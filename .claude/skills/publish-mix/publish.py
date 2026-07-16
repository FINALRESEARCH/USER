#!/usr/bin/env python3
"""publish.py — deterministic steps for the evenings -> Are.na publishing pipeline.

Stdlib only (no pip install). Each subcommand is independently runnable so the
/publish-mix skill (or a human) can call one step at a time and inspect output.

Subcommands:
  recent   [--limit N] [--station] -> list recent evenings tracks to pick from (JSON)
  list     [--search S] [--json]   -> list your evenings tracks (newest first)
  resolve  <track-id|url>          -> print evenings file URL + metadata (JSON)
  download <url> <dest>            -> stream the mp3 to a local file
  ingest   <url> [--title T]       -> create Are.na block directly from a URL (zero transfer)
  upload   [file] [--url U] [--title T] -> presign + PUT + create block (local file or streamed)
  set-meta <block-id> [...]        -> PUT title/description onto a block
  block-get <block-id>             -> fetch a block (verification)
  revalidate                       -> POST the live site's revalidate route (busts the 'mixes' ISR tag)

Avoiding the local round-trip for big mixes: prefer `ingest <evenings-file-url>` —
Are.na fetches and re-hosts the file server-side, so no bytes pass through this
machine. If Are.na ever returns a bare Link instead of a re-hosted Attachment
(check the `rehosted` field), fall back to `upload --url <evenings-file-url>`,
which streams the source straight into the presigned S3 PUT without touching disk.

Config via env (loaded from ./.env if present):
  EVENINGS_API_KEY, ARENA_TOKEN, ARENA_CHANNEL
  EVENINGS_API_BASE (default https://api.evenings.co/v1)
  ARENA_API_BASE    (default https://api.are.na/v3)
  SITE_URL, REVALIDATE_SECRET (for the `revalidate` subcommand; see WEBAPP.md)
"""
import argparse
import json
import os
import re
import sys
import time
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


def cmd_recent(args):
    """List recent evenings tracks so the user can pick one to publish.

    The exact listing endpoint/shape is a known-unknown (see CLAUDE.md): tracks
    are scoped to a station on evenings.fm. We default to /tracks, allow a
    station override (arg or EVENINGS_STATION), tolerate common list wrappers,
    and surface the raw body if no list is found instead of guessing.
    """
    key = env("EVENINGS_API_KEY", required=True)
    base = env("EVENINGS_API_BASE", EVENINGS_API_BASE)
    station = args.station or env("EVENINGS_STATION")
    path = f"/stations/{urllib.parse.quote(str(station))}/tracks" if station else "/tracks"
    query = urllib.parse.urlencode({"limit": args.limit})
    _, body, _ = request(
        "GET", f"{base}{path}?{query}",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )

    items = None
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        for key_name in ("tracks", "data", "results", "items"):
            if isinstance(body.get(key_name), list):
                items = body[key_name]
                break
    if items is None:
        # Don't guess the field name — surface the raw body so it can be identified.
        print(json.dumps({
            "error": "could not find a track list in the response",
            "path": path,
            "raw": body,
        }, indent=2))
        return

    out = []
    for track in items[: args.limit]:
        if not isinstance(track, dict):
            continue
        out.append({
            "id": first(track, "id", "track_id"),
            "title": first(track, "title", "name"),
            "duration": first(track, "duration"),
            "created_at": first(track, "created_at", "created", "published_at", "date"),
            "station": first(track, "station.slug", "station_slug", "station"),
        })
    print(json.dumps(out, indent=2))


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


def arena_create_block(base, token, value, channel, title=None):
    """POST a block into the channel from a URL `value` and return the block dict.

    Are.na fetches `value` server-side; for a media URL it re-hosts the file as an
    Attachment. This is used for both the temp-bucket value (streaming upload) and
    a direct source URL (zero-transfer ingest). POST /blocks takes a flat
    `channel_ids` array; per the v3 OpenAPI spec it accepts slugs as well as
    numeric ids. The old `channels:[{id}]` form was silently ignored, creating
    orphaned blocks. (Verified 2026-06-18.)"""
    payload = {"value": value, "channel_ids": [channel]}
    if title:
        payload["title"] = title
    _, block, _ = request(
        "POST", f"{base}/blocks", headers=arena_headers(token),
        data=json.dumps(payload).encode(),
    )
    return block


def arena_wait_for_block(base, token, block_id, tries=20, delay=3):
    """Poll a block until it leaves the `processing` state (Are.na transcodes
    async). Returns the final block dict (or the last seen one)."""
    block = {}
    for _ in range(tries):
        _, block, _ = request(
            "GET", f"{base}/blocks/{urllib.parse.quote(str(block_id))}",
            headers=arena_headers(token, json_body=False),
        )
        if block.get("state") != "processing":
            return block
        time.sleep(delay)
    return block


def _block_report(block, base, token, **extra):
    """Wait for processing to finish, then print a uniform result summary that
    records whether Are.na actually re-hosted the file (Attachment) vs. left it a
    bare Link — so the caller knows if a streaming fallback is needed."""
    block_id = first(block, "id", "block.id")
    final = arena_wait_for_block(base, token, block_id) if block_id else block
    att = final.get("attachment") if isinstance(final, dict) else None
    att_url = (att or {}).get("url") or ""
    out = {
        "block_id": block_id,
        "arena_url": f"https://www.are.na/block/{block_id}" if block_id else None,
        "state": final.get("state") if isinstance(final, dict) else None,
        "type": final.get("type") if isinstance(final, dict) else None,
        # True once the bytes live on Are.na's own attachments host (durable).
        "rehosted": att_url.startswith("https://attachments.are.na/"),
        "attachment": att,
    }
    out.update(extra)
    print(json.dumps(out, indent=2))


def cmd_ingest(args):
    """Zero-transfer path: hand Are.na the source URL and let it fetch + re-host
    the file server-side. No download, no presign, no PUT — nothing flows through
    this machine. Verifies the result is a re-hosted Attachment, not a bare Link."""
    token = env("ARENA_TOKEN", required=True)
    channel = env("ARENA_CHANNEL", required=True)
    base = env("ARENA_API_BASE", ARENA_API_BASE)
    block = arena_create_block(base, token, args.url, channel, title=args.title)
    _block_report(block, base, token, method="ingest", source_url=args.url)


def _arena_presign(base, token, filename, content_type):
    """POST /uploads/presign and return (upload_url, key) for a single file."""
    _, presign, _ = request(
        "POST", f"{base}/uploads/presign",
        headers=arena_headers(token),
        data=json.dumps({"files": [{"filename": filename, "content_type": content_type}]}).encode(),
    )
    files = presign.get("files") if isinstance(presign, dict) else None
    entry = files[0] if isinstance(files, list) and files else presign
    upload_url = first(entry, "upload_url", "url")
    obj_key = first(entry, "key")
    if not upload_url or not obj_key:
        die(f"unexpected presign response: {json.dumps(presign)}")
    return upload_url, obj_key


def cmd_upload(args):
    """Upload to Are.na's temp bucket then create the block. Source is either a
    local --file (read into memory) or a --url that is *streamed* straight from
    its host into the presigned S3 PUT — no local file, constant memory — so a
    100 MB mix never lands on disk. Used as the reliable fallback when direct
    `ingest` would yield a bare Link instead of a re-hosted Attachment."""
    token = env("ARENA_TOKEN", required=True)
    channel = env("ARENA_CHANNEL", required=True)
    base = env("ARENA_API_BASE", ARENA_API_BASE)
    content_type = "audio/mpeg"

    if args.url:
        # Stream: open the source GET and feed the response object directly as
        # the PUT body. http.client reads it in 8 KB blocks; passing the source's
        # Content-Length keeps S3 happy (no chunked encoding) and memory flat.
        src = urllib.request.urlopen(
            urllib.request.Request(args.url, headers={"User-Agent": USER_AGENT})
        )
        length = src.headers.get("Content-Length")
        filename = args.title and re.sub(r"[^\w.-]+", "_", args.title) + ".mp3"
        filename = filename or os.path.basename(urllib.parse.urlparse(args.url).path) or "mix.mp3"
        upload_url, obj_key = _arena_presign(base, token, filename, content_type)
        put_headers = {"Content-Type": content_type}
        if length:
            put_headers["Content-Length"] = length
        request("PUT", upload_url, headers=put_headers, data=src, expect_json=False)
        uploaded_mb = round(int(length) / 1_000_000, 1) if length else None
    else:
        path = args.file
        if not path or not os.path.exists(path):
            die(f"file not found: {path!r} (pass a local --file path or --url to stream)")
        filename = os.path.basename(path)
        upload_url, obj_key = _arena_presign(base, token, filename, content_type)
        with open(path, "rb") as fh:
            raw = fh.read()
        request("PUT", upload_url, headers={"Content-Type": content_type},
                data=raw, expect_json=False)
        uploaded_mb = round(len(raw) / 1_000_000, 1)

    value = ARENA_TEMP_URL.format(key=obj_key)
    block = arena_create_block(base, token, value, channel, title=args.title)
    _block_report(block, base, token, method=("stream" if args.url else "file"),
                  uploaded_mb=uploaded_mb)


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


# -------------------------------------------------------------------- revalidate
def cmd_revalidate(args):
    """Tell the live Next.js site its Are.na data changed, so it busts the ISR
    'mixes' tag instead of waiting for the daily cron (see WEBAPP.md). Call this
    after any channel edit — set-meta, a new ingest/upload, or a manual
    connect/disconnect (e.g. swapping a block for a re-upload)."""
    site = env("SITE_URL", required=True)
    secret = env("REVALIDATE_SECRET", required=True)
    _, body, _ = request(
        "POST", f"{site.rstrip('/')}/api/revalidate",
        headers={"x-secret": secret, "Accept": "application/json"},
        data=b"",
    )
    print(json.dumps({"site": site, "response": body}, indent=2))


# ------------------------------------------------------------------------ main
def build_parser():
    p = argparse.ArgumentParser(description="evenings -> Are.na publishing helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    rc = sub.add_parser("recent", help="list recent evenings tracks to pick from")
    rc.add_argument("--limit", type=int, default=10)
    rc.add_argument("--station", help="station slug (defaults to EVENINGS_STATION env if set)")
    rc.set_defaults(func=cmd_recent)

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

    i = sub.add_parser("ingest", help="create a block directly from a source URL (zero transfer)")
    i.add_argument("url")
    i.add_argument("--title")
    i.set_defaults(func=cmd_ingest)

    u = sub.add_parser("upload", help="upload a local file or stream a --url into Are.na as a block")
    u.add_argument("file", nargs="?", help="local file path (omit when using --url)")
    u.add_argument("--url", help="stream from this URL instead of a local file (no disk)")
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

    rv = sub.add_parser("revalidate", help="POST the live site's revalidate route (bust ISR cache)")
    rv.set_defaults(func=cmd_revalidate)
    return p


def main():
    load_dotenv()
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
