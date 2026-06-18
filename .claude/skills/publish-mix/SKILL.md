---
name: publish-mix
description: Publish a DJ mix from evenings.fm to an Are.na channel with a formatted tracklist and per-track buy/Bandcamp/YouTube links. Use when the user wants to publish, post, or upload a finished evenings mix, or runs /publish-mix with an evenings track URL or id.
---

# publish-mix

Publishes one finished mix: **evenings.fm → Are.na channel → block with tracklist + links.**

The deterministic API calls live in `publish.py` (in this skill folder, stdlib only). Run it from
the **repo root** as `python3 .claude/skills/publish-mix/publish.py <subcommand>`. Secrets come from
env (`.env` locally, environment secrets in cloud sessions): `EVENINGS_API_KEY`, `ARENA_TOKEN`,
`ARENA_CHANNEL`. If any is missing, stop and tell the user which to set — never invent values.

## Input
The user invokes `/publish-mix <evenings-track-url-or-id>` (e.g. a full
`https://evenings.fm/<station>/tracks/8389` URL or just `8389`). If no argument was given, ask for it.

## Steps

1. **Resolve.** Run `publish.py resolve <arg>`. Show the user the resolved `file_url`, `title`, and
   size/duration if present. If `file_url` is empty, report the raw `url`/`location` values and stop
   (the evenings field name may have changed — surface it, don't guess).

2. **Download.** Run `publish.py download <file_url> downloads/<safe-filename>.mp3`. Report the MB.

3. **Upload to Are.na.** Run `publish.py upload downloads/<file>.mp3 --title "<mix title>"`.
   - Capture `block_id` from the JSON.
   - **File-size gate:** if upload fails with a size/413 error, STOP and tell the user Are.na
     rejected the ~100 MB file — the fallback is hosting the file on Cloudflare R2 instead (see
     CLAUDE.md). Do not retry blindly.

4. **Tracklist.** Ask the user to paste the raw tracklist. Parse flexibly into an ordered list of
   `{n, artist, title, timestamp?}` — handle `1. Artist – Title 12:34`, `Artist - Title`, en/em
   dashes, optional timestamps. Echo the normalized list back and ask them to confirm it parsed
   correctly before proceeding.

5. **Link enrichment (auto-search + confirm).** For each track:
   - Use `WebSearch` for the track on **Bandcamp** and **YouTube** (e.g. `"<artist> <title>" bandcamp`
     and `"<artist> <title>" youtube`). There is no Bandcamp API — search-and-confirm is expected.
   - Propose the single best candidate link (prefer Bandcamp for "buy", else YouTube).
   - Use `AskUserQuestion` to let the user **accept / pick another / paste a correction / skip**.
     Batch several tracks per question turn to keep it fast; skipped tracks get no link.

6. **Write description.** Build a markdown description:
   - First line: the mix title (and date if known).
   - Then a numbered tracklist; each line `n. [Artist – Title](confirmed-url)` (timestamp prefix if
     present). Tracks with no link are plain text.
   - Write it to a temp file `downloads/desc.md` and run
     `publish.py set-meta <block_id> --title "<mix title>" --description-file downloads/desc.md`.
   - **Markdown gate:** after setting, run `publish.py block-get <block_id>` and check the
     description came back intact. If markdown links clearly don't render on Are.na, re-run with a
     plain `Artist – Title — <url>` description instead and tell the user.

7. **Report.** Print the Are.na block URL, file size, #tracks, #links set. Remind the user the local
   mp3 in `downloads/` is their working copy (masters belong on the Synology archive); it is
   gitignored and won't be committed.

## Notes
- Keep the user in control: confirm the parsed tracklist and each link before writing.
- Never commit `.env`, `downloads/`, or mp3s (already gitignored).
- If env vars are absent in a cloud/phone session, they must be set as Claude Code environment
  secrets — point the user to CLAUDE.md.
