# Project context for Claude Code

## What this is
A manually-run pipeline that publishes a DJ mix from **evenings.fm** to an **Are.na** channel with
a formatted tracklist + per-track links. Entry point: the `/publish-mix` skill in
`.claude/skills/publish-mix/`. The deterministic API work lives in `publish.py` (Python stdlib only,
so it runs anywhere including cloud/phone sessions — no `pip install`).

## How to run
`/publish-mix <evenings-track-url-or-id>` — the skill orchestrates:
1. `resolve` the evenings track → direct mp3 URL + metadata.
2. `download` the mp3 to `downloads/`.
3. `upload` to the Are.na channel (presign → S3 PUT → create block) → returns a block id.
4. User pastes a tracklist; skill parses it.
5. For each track, `WebSearch` Bandcamp + YouTube → user confirms the link (`AskUserQuestion`).
6. `set-meta` writes the title + markdown tracklist into the block description.

## Required environment variables
- `EVENINGS_API_KEY` — evenings personal API key (Bearer).
- `ARENA_TOKEN` — Are.na personal access token (Bearer).
- `ARENA_CHANNEL` — target Are.na channel slug or id.
- Optional: `EVENINGS_API_BASE` (default `https://api.evenings.co/v1`),
  `ARENA_API_BASE` (default `https://api.are.na/v3`).

Locally these come from a gitignored `.env`. **In cloud/phone sessions, set them as Claude Code
environment secrets** — the sandbox cannot read the local `.env`.

## Known unknowns (verify on first real run; don't assume)
1. **Are.na attachment file-size limit** — undocumented; mixes are ~100 MB. If `upload` is rejected,
   switch the file host to **Cloudflare R2** (only `upload` + the served base URL change).
2. **Block update fields / markdown** — `PUT /v3/blocks/{id}` field names (`title`, `description`)
   and whether the description renders markdown links are unconfirmed. If links don't render, fall
   back to plain `Artist – Title — <url>` lines (the helper supports a `--plain` description mode).
3. **Evenings file field** — track responses carry both `url` and `location`; `publish.py resolve`
   picks whichever looks like the actual audio file (`.mp3`/`audio` content-type), printing both.
4. **Are.na API base/host** — endpoints are documented as `/v3/...`; if the host/path differs,
   override with `ARENA_API_BASE`.

## Conventions
- No external Python deps. Secrets only via env. Never commit `.env` or media files.
- Keep `publish.py` subcommands small and independently runnable so the skill (and a human) can
  call each step and inspect output.
