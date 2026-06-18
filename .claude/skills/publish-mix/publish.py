#!/usr/bin/env python3
"""publish.py — deterministic steps for the evenings -> Are.na publishing pipeline.

Stdlib only (no pip install). Each subcommand is independently runnable so the
/publish-mix skill (or a human) can call one step at a time and inspect output.

Subcommands:
  list     [--search S] [--json]   -> list your evenings tracks (newest first)
  resolve  <track-id|url>          -> print evenings file URL + metadata (JSON)
  download <url> <dest>            -> stream the mp3 to a local file
  upload   <file> [--title T]      -> presign + PUT + create Are.na block (prints JSON)
  set-meta <block-id> [...]        -> PUT title/description onto a block
  block-get <block-id>             -> fetch a block (verification)

Config via env (loaded from ./.env if present):
  EVENINGS_API_KEY, ARENA_TOKEN, ARENA_CHANNEL
  EVENINGS_API_BASE (default https://api.evenings.co/v1)
  ARENA_API_BASE    (default https://api.are.na/v3)
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

EVENINGS_API_BASE = "https://api.evenings.co/v1"
ARENA_API_BASE = "https://api.are.na/v3"
ARENA_TEMP_URL = "https://s3.amazonaws.com/arena_images-temp/{key}"

# Are.na sits behind Cloudflare, which rejects urllib's default request
# signature with "Error 1010: Access denied". A browser-like User-Agent on
# every request avoids it. (Verified on first real run, 2026-06-18.)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# --------------------------------------------------------------------------- env
def load_dotenv(path=".env"):
    """Minimal .env loader; does not override already-set env vars."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


def env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        die(f"Missing required env var: {name} (set it in .env or as an environment secret)")
    return val


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ----------------------------------------------------------------------- http
def request(method, url, headers=None, data=None, expect_json=True):
    headers = dict(headers or {})
    headers.setdefault("User-Agent", USER_AGENT)
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            if not expect_json:
                return resp.status, body, dict(resp.headers)
            text = body.decode("utf-8") if body else ""
            return resp.status, (json.loads(text) if text else {}), dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        die(f"HTTP {e.code} {method} {url}\n{detail}")
    except urllib.error.URLError as e:
        die(f"network error {method} {url}: {e.reason}")


def first(d, *keys):
    """Return the first present, non-empty value among keys (supports nesting via 'a.b')."""
    for key in keys:
        cur = d
        ok = True
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, "", []):
            return cur
    return None


# -------------------------------------------------------------------- evenings
def track_id_from_arg(arg):
    """Accept a bare id or a full evenings URL like .../tracks/8389."""
    m = re.search(r"/tracks/([^/?#]+)", arg)
    return m.group(1) if m else arg


def cmd_resolve(args):
    key = env("EVENINGS_API_KEY", required=True)
    base = env("EVENINGS_API_BASE", EVENINGS_API_BASE)
    tid = track_id_from_arg(args.track)
    _, body, _ = request(
        "GET", f"{base}/tracks/{urllib.parse.quote(str(tid))}",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    track = body.get("track", body.get("data", body))  # tolerate wrappers
    file_url = first(track, "location", "url")
    out = {
        "id": tid,
        "file_url": file_url,
        "url": track.get("url"),
        "location": track.get("location"),
        "title": first(track, "title"),
        "filename": first(track, "filename"),
        "filetype": first(track, "filetype"),
        "duration": first(track, "duration"),
        "image": first(track, "image"),
    }
    print(json.dumps(out, indent=2))


def fmt_duration(seconds):
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "?"
    return f"{s // 60}:{s % 60:02d}"


def cmd_list(args):
    key = env("EVENINGS_API_KEY", required=True)
    base = env("EVENINGS_API_BASE", EVENINGS_API_BASE)
    _, body, _ = request(
        "GET", f"{base}/tracks",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    tracks = body if isinstance(body, list) else body.get("tracks", body.get("data", []))

    if args.search:
        needle = args.search.lower()
        tracks = [t for t in tracks if needle in (t.get("title") or "").lower()]

    # newest first by streamedAt/createdAt (ISO 8601 strings sort lexically)
    tracks.sort(key=lambda t: t.get("streamedAt") or t.get("createdAt") or "", reverse=True)

    if args.json:
        print(json.dumps(tracks, indent=2))
        return

    if not tracks:
        print("no tracks found" + (f" matching {args.search!r}" if args.search else ""))
        return

    print(f"{'id':>6}  {'dur':>7}  {'date':<10}  {'pub':<3}  title")
    for t in tracks:
        date = (t.get("streamedAt") or t.get("createdAt") or "")[:10]
        pub = "yes" if t.get("published") else "no"
        title = t.get("title") or "(untitled)"
        print(f"{t.get('id'):>6}  {fmt_duration(t.get('duration')):>7}  {date:<10}  {pub:<3}  {title}")
    print(f"\n{len(tracks)} track(s). Publish one with: /publish-mix <id>")


def cmd_download(args):
    status, body, headers = request("GET", args.url, expect_json=False)
    with open(args.dest, "wb") as fh:
        fh.write(body)
    size = os.path.getsize(args.dest)
    print(json.dumps({
        "dest": args.dest,
        "bytes": size,
        "mb": round(size / 1_000_000, 1),
        "content_type": headers.get("Content-Type"),
    }, indent=2))


# ----------------------------------------------------------------------- arena
def arena_headers(token, json_body=True):
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def cmd_upload(args):
    token = env("ARENA_TOKEN", required=True)
    channel = env("ARENA_CHANNEL", required=True)
    base = env("ARENA_API_BASE", ARENA_API_BASE)
    path = args.file
    if not os.path.exists(path):
        die(f"file not found: {path}")
    filename = os.path.basename(path)
    content_type = "audio/mpeg"

    # 1) presign — Are.na expects a `files` array of {filename, content_type};
    # the response echoes it back as `files[i]` with upload_url + key. (Verified 2026-06-18.)
    _, presign, _ = request(
        "POST", f"{base}/uploads/presign",
        headers=arena_headers(token),
        data=json.dumps({"files": [{"filename": filename, "content_type": content_type}]}).encode(),
    )
    files = presign.get("files") if isinstance(presign, dict) else None
    if not files:
        die(f"unexpected presign response: {json.dumps(presign)}")
    upload_url = first(files[0], "upload_url", "url")
    obj_key = first(files[0], "key")
    if not upload_url or not obj_key:
        die(f"unexpected presign response: {json.dumps(presign)}")

    # 2) PUT bytes to S3
    with open(path, "rb") as fh:
        raw = fh.read()
    request("PUT", upload_url, headers={"Content-Type": content_type},
            data=raw, expect_json=False)

    # 3) create the block AND connect it to the channel in one call.
    # POST /blocks takes a flat `channel_ids` array; per the v3 OpenAPI spec it
    # accepts slugs as well as numeric ids. The old `channels:[{id}]` form was
    # silently ignored, creating orphaned blocks. (Verified 2026-06-18.)
    value = ARENA_TEMP_URL.format(key=obj_key)
    payload = {"value": value, "channel_ids": [channel]}
    if args.title:
        payload["title"] = args.title
    _, block, _ = request(
        "POST", f"{base}/blocks", headers=arena_headers(token),
        data=json.dumps(payload).encode(),
    )
    block_id = first(block, "id", "block.id")
    if not block_id:
        die(f"block create returned no id: {json.dumps(block)[:200]}")
    print(json.dumps({
        "block_id": block_id,
        "channel": channel,
        "arena_url": f"https://www.are.na/block/{block_id}",
        "uploaded_mb": round(len(raw) / 1_000_000, 1),
    }, indent=2))


def cmd_set_meta(args):
    token = env("ARENA_TOKEN", required=True)
    base = env("ARENA_API_BASE", ARENA_API_BASE)
    payload = {}
    if args.title:
        payload["title"] = args.title
    if args.description_file:
        with open(args.description_file, "r", encoding="utf-8") as fh:
            payload["description"] = fh.read()
    elif args.description:
        payload["description"] = args.description
    if not payload:
        die("nothing to set: pass --title and/or --description/--description-file")
    _, body, _ = request(
        "PUT", f"{base}/blocks/{urllib.parse.quote(str(args.block_id))}",
        headers=arena_headers(token), data=json.dumps(payload).encode(),
    )
    print(json.dumps({"block_id": args.block_id, "updated": list(payload), "raw": body}, indent=2))


def cmd_block_get(args):
    token = env("ARENA_TOKEN", required=True)
    base = env("ARENA_API_BASE", ARENA_API_BASE)
    _, body, _ = request(
        "GET", f"{base}/blocks/{urllib.parse.quote(str(args.block_id))}",
        headers=arena_headers(token, json_body=False),
    )
    print(json.dumps(body, indent=2))


# ------------------------------------------------------------------------ main
def build_parser():
    p = argparse.ArgumentParser(description="evenings -> Are.na publishing helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("list", help="list your evenings tracks (newest first)")
    l.add_argument("--search", help="filter by title substring (case-insensitive)")
    l.add_argument("--json", action="store_true", help="emit raw track JSON")
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("resolve", help="evenings track id/url -> file URL + metadata")
    r.add_argument("track")
    r.set_defaults(func=cmd_resolve)

    d = sub.add_parser("download", help="download a URL to a file")
    d.add_argument("url")
    d.add_argument("dest")
    d.set_defaults(func=cmd_download)

    u = sub.add_parser("upload", help="upload a file to Are.na channel as a block")
    u.add_argument("file")
    u.add_argument("--title")
    u.set_defaults(func=cmd_upload)

    s = sub.add_parser("set-meta", help="set title/description on a block")
    s.add_argument("block_id")
    s.add_argument("--title")
    s.add_argument("--description")
    s.add_argument("--description-file")
    s.set_defaults(func=cmd_set_meta)

    g = sub.add_parser("block-get", help="fetch a block (verification)")
    g.add_argument("block_id")
    g.set_defaults(func=cmd_block_get)
    return p


def main():
    load_dotenv()
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
