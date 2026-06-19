# Project context for Claude Code

## What this is
A manually-run pipeline that publishes a DJ mix from **evenings.fm** to an **Are.na** channel with
a formatted tracklist + per-track links. Entry point: the `/publish-mix` skill in
`.claude/skills/publish-mix/`. The deterministic API work lives in `publish.py` (Python stdlib only,
so it runs anywhere including cloud/phone sessions — no `pip install`).

## How to run
`/publish-mix <evenings-track-url-or-id>` — the skill orchestrates:
1. `resolve` the evenings track → direct mp3 URL + metadata.
2. `ingest` that URL into the Are.na channel — Are.na fetches + re-hosts it server-side, so no
   bytes pass through this machine (important for ~100 MB mixes). Falls back to `upload --url`
   (streams source → presigned PUT, no disk), then to `download` + local `upload` only if needed.
   Returns a block id.
3. User pastes a tracklist; skill parses it.
4. For each track, `WebSearch` Bandcamp + YouTube → user confirms the link (`AskUserQuestion`).
5. `set-meta` writes the title + markdown tracklist into the block description.

## Verified Are.na API behavior (confirmed on a real run 2026-06, mp3 ~5 MB)
- **Presign body shape:** `POST /v3/uploads/presign` requires `{"files":[{filename, content_type}]}`
  (a `files` array at the root) and returns a matching `files` array of `{upload_url, key, content_type}`.
- **Cloudflare UA ban:** api.are.na (behind Cloudflare) 403s the default `Python-urllib` user-agent
  (error 1010). `publish.py` sends a browser User-Agent on every request.
- **Direct URL ingest re-hosts:** `POST /v3/blocks {value:<any media url>, channels:[...]}` makes
  Are.na fetch the URL and create a re-hosted `Attachment` (served from `attachments.are.na`), not a
  bare Link — same byte count, with the source recorded under `source`. This is the zero-transfer path.
- **Block creation is async:** the block returns `PendingBlock`/`state:processing`; poll
  `GET /v3/blocks/{id}` until `state` ≠ `processing`. `rehosted:true` in helper output ⇒ durable copy.
- **Deleting a block from a channel:** `DELETE /v3/connections/{connection_id}` → 204. The
  connection id comes from `GET /v3/channels/{slug}/contents` (`item.connection.id`). Block-level
  `DELETE /v3/blocks/{id}` is 405; `…/channels/{slug}/blocks/{id}` is 404.

## Required environment variables
- `EVENINGS_API_KEY` — evenings personal API key (Bearer).
- `ARENA_TOKEN` — Are.na personal access token (Bearer).
- `ARENA_CHANNEL` — target Are.na channel slug or id.
- Optional: `EVENINGS_API_BASE` (default `https://api.evenings.co/v1`),
  `ARENA_API_BASE` (default `https://api.are.na/v3`),
  `EVENINGS_STATION` (station slug for `publish.py recent`'s "pick a mix" listing).

Locally these come from a gitignored `.env`. **In cloud/phone sessions, set them as Claude Code
environment secrets** — the sandbox cannot read the local `.env`.

## Known unknowns (verify on first real run; don't assume)
1. **Are.na attachment file-size limit** — undocumented; small files (~5 MB) confirmed working, but
   the ~100 MB case is still unverified. With `ingest`/`upload --url` the limit is enforced by
   Are.na's own fetcher, not by us. If a large file is rejected (size/413), switch the file host to
   **Cloudflare R2** (only the served base URL changes; still ingestible via `ingest <r2-url>`).
2. **Block update fields / markdown** — `PUT /v3/blocks/{id}` field names (`title`, `description`)
   and whether the description renders markdown links are unconfirmed. If links don't render, fall
   back to plain `Artist – Title — <url>` lines (the helper supports a `--plain` description mode).
3. **Evenings file field** — track responses carry both `url` and `location`; `publish.py resolve`
   picks whichever looks like the actual audio file (`.mp3`/`audio` content-type), printing both.
4. **Evenings recent-tracks listing** — `publish.py recent` powers the "pick a mix" prompt when
   `/publish-mix` is run with no argument. The listing endpoint/shape is unconfirmed: it defaults to
   `GET /tracks?limit=N`, allows a per-station path via `--station`/`EVENINGS_STATION`
   (`/stations/<slug>/tracks`), and tolerates `tracks`/`data`/`results`/`items` list wrappers. If it
   can't find a list it prints the raw body so the real field/path can be identified — don't guess.
5. **Are.na API base/host** — endpoints are documented as `/v3/...`; if the host/path differs,
   override with `ARENA_API_BASE`.

## Conventions
- No external Python deps. Secrets only via env. Never commit `.env` or media files.
- Keep `publish.py` subcommands small and independently runnable so the skill (and a human) can
  call each step and inspect output.
