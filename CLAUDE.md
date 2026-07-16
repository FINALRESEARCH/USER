# Project context for Claude Code

## What this is
A manually-run pipeline that publishes a DJ mix from **evenings.fm** to an **Are.na** channel with
a formatted tracklist + per-track links. Entry point: the `/publish-mix` skill in
`.claude/skills/publish-mix/`. The deterministic API work lives in `publish.py` (Python stdlib only,
so it runs anywhere including cloud/phone sessions — no `pip install`).

The **Next.js site** (repo root — `app/`, `components/`, `lib/`) that displays the published mixes is
the *read* side; its API contract, gotchas, and Vercel free-tier strategy are in **`WEBAPP.md`**.

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
6. `revalidate` POSTs the live site's `/api/revalidate` route so it picks up the change immediately
   instead of waiting for the daily cron (see `WEBAPP.md`). Also re-run this after any manual edit to
   the Are.na channel (swapping a block, disconnecting one, hand-editing a description).

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
- `ARENA_CHANNEL` — target Are.na channel slug or id. **Verify this against the actual channel
  before trusting it** — nothing validates it at rest, and a stale/wrong slug 404s silently until
  you try to use it (this happened once already: the env var pointed at a nonexistent slug that
  looked plausible instead of the real channel, `fr_20_p_user`).
- Optional: `EVENINGS_API_BASE` (default `https://api.evenings.co/v1`),
  `ARENA_API_BASE` (default `https://api.are.na/v3`),
  `EVENINGS_STATION` (station slug for `publish.py recent`'s "pick a mix" listing).
- For the `publish.py revalidate` step (see WEBAPP.md): `SITE_URL` (the live site's base URL) and
  `REVALIDATE_SECRET` (shared secret, must match the `REVALIDATE_SECRET` set on the Vercel project).
  Not required for the Are.na publish itself — if unset, `revalidate` fails and the skill should say
  so rather than block the rest of the flow.

Locally these come from a gitignored `.env`. **In cloud/phone sessions, set them as Claude Code
environment secrets** — the sandbox cannot read the local `.env`. Note also that a cloud/phone
session's outbound network is policy-restricted to an allowlist of hosts; `SITE_URL`'s host may need
to be added to that allowlist before `revalidate` can succeed from such a session (it works fine from
a local machine's unrestricted network regardless).

## Verified facts (resolved on first real run, 2026-06-18 — block 47135727)
1. **Are.na attachment file-size limit** — RESOLVED: a 142 MB mp3 uploaded fine. R2 fallback not needed.
2. **Block update fields / markdown** — RESOLVED: `PUT /v3/blocks/{id}` takes `title` + `description`,
   and markdown **including links renders** (`[t](url)` → real `<a href>`). Note: on read-back
   `description` is an OBJECT `{markdown, html, plain}`, not a string — check `description.markdown`.
3. **Evenings file field** — RESOLVED: audio lives in `location` (`url` is usually null);
   `resolve` prints both and picks `location`.
4. **Are.na API base/host** — RESOLVED: v3 at `https://api.are.na` ("Are.na API 3.0.0"). The token is a
   v3 personal access token and is rejected by the v2 API (401) — stay on v3.
5. **Evenings recent-tracks listing** — `publish.py recent` powers the "pick a mix" prompt when
   `/publish-mix` is run with no argument. The listing endpoint/shape is unconfirmed: it defaults to
   `GET /tracks?limit=N`, allows a per-station path via `--station`/`EVENINGS_STATION`
   (`/stations/<slug>/tracks`), and tolerates `tracks`/`data`/`results`/`items` list wrappers. If it
   can't find a list it prints the raw body so the real field/path can be identified — don't guess.

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
