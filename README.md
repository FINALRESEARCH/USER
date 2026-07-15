# USER

Publishing pipeline for DJ mixes: **evenings.fm → Are.na → (future site)**.

Record a mix on [evenings.fm](https://evenings.fm); run the `/publish-mix` Claude Code skill to
download it, upload it to an Are.na channel, and attach a formatted tracklist with per-track
buy/Bandcamp/YouTube links. The Are.na channel becomes the canonical, site-ready source of mixes.

## Quick start

```bash
cp .env.example .env   # fill in EVENINGS_API_KEY, ARENA_TOKEN, ARENA_CHANNEL
```

Then in Claude Code:

```
/publish-mix https://evenings.fm/<station>/tracks/<id>
```

The skill walks you through: resolve → download → upload to Are.na → paste tracklist →
confirm auto-searched links → write the block description.

## Manual helper usage

`publish.py` (stdlib only, no pip install needed) can also be driven directly:

```bash
python3 .claude/skills/publish-mix/publish.py list               # browse your tracks (newest first)
python3 .claude/skills/publish-mix/publish.py list --search nautiluss
python3 .claude/skills/publish-mix/publish.py resolve 8389
python3 .claude/skills/publish-mix/publish.py download <url> downloads/mix.mp3
python3 .claude/skills/publish-mix/publish.py upload downloads/mix.mp3 --title "Mix title"
python3 .claude/skills/publish-mix/publish.py set-meta <block-id> --title "..." --description-file desc.md
```

## Building from the phone

This project is wired for Claude Code on the web/mobile. See `CLAUDE.md` for context and the
secrets that must be set as Claude Code **environment secrets** (the cloud sandbox can't read your
local `.env`).

## Status of open assumptions

See `CLAUDE.md → Known unknowns`. The big ones: Are.na's attachment **file-size limit** (mixes are
~100 MB) and whether the block **description renders markdown links**. Both are verified on first
real run; if file size fails, files move to Cloudflare R2 (pipeline shape unchanged).
