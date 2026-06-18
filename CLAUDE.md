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

## Verified facts (resolved on first real run, 2026-06-18 — block 47135727)
1. **Are.na attachment file-size limit** — RESOLVED: a 142 MB mp3 uploaded fine. R2 fallback not needed.
2. **Block update fields / markdown** — RESOLVED: `PUT /v3/blocks/{id}` takes `title` + `description`,
   and markdown **including links renders** (`[t](url)` → real `<a href>`). Note: on read-back
   `description` is an OBJECT `{markdown, html, plain}`, not a string — check `description.markdown`.
3. **Evenings file field** — RESOLVED: audio lives in `location` (`url` is usually null);
   `resolve` prints both and picks `location`.
4. **Are.na API base/host** — RESOLVED: v3 at `https://api.are.na` ("Are.na API 3.0.0"). The token is a
   v3 personal access token and is rejected by the v2 API (401) — stay on v3.

## v3 API gotchas (learned the hard way — keep these)
- **User-Agent required**: Are.na is behind Cloudflare; urllib's default UA gets Error 1010. `publish.py`
  sets a browser UA on every request.
- **presign body**: `POST /v3/uploads/presign` wants `{"files":[{"filename","content_type"}]}` (array),
  and echoes back `files[i].{upload_url,key}`.
- **create + connect in ONE call**: `POST /v3/blocks` with a flat `channel_ids` array (accepts slugs OR
  numeric ids). The old `channels:[{id}]` form is silently ignored → orphaned blocks. To disconnect,
  `DELETE /v3/connections/{connection_id}` (the connection id is nested at channel-content `connection.id`,
  NOT the channel id; `DELETE /v3/blocks/{id}` is 405).
- Spec reference: Are.na's OpenAPI lives in the `aredotna/mcp` repo at `src/generated/openapi.json`.

## Conventions
- No external Python deps. Secrets only via env. Never commit `.env` or media files.
- Keep `publish.py` subcommands small and independently runnable so the skill (and a human) can
  call each step and inspect output.
