# Web app notes (read side: Are.na → Next.js site)

> Scratch/handoff doc for the future Next.js site that displays the published mixes.
> **Fold into CLAUDE.md during repo cleanup.** The publishing half (`publish.py` + the
> `/publish-mix` skill) is the *write* side; this is the *read* side. They are decoupled —
> the Are.na channel is the contract, not a function call. The Next app never runs the Python.

## Architecture in one line
`evenings → publish.py → Are.na channel (fr_20_p_music) → Next.js reads channel → static site`

## The single read call
One request returns everything per mix — no per-track or per-block fan-out:

```
GET https://api.are.na/v3/channels/fr_20_p_music/contents
```

Per item (one Attachment block = one mix), the site uses:

| Field | Use |
|---|---|
| `title` | Mix title |
| `attachment.url` | Audio source — permanent are.na CDN URL (`attachments.are.na/…`) |
| `image.src` | Cover, full res (CDN) |
| `image.small.src` | Cover thumbnail (pre-resized by are.na) |
| `image.blurhash` / `image.aspect_ratio` | Progressive loading / layout |
| `description.html` | Rendered tracklist — already has clickable `<a href … target rel>` anchors |
| `connection.id` / `connection.position` | Ordering / per-mix identity |

## Read-side contracts (learned the hard way — see CLAUDE.md gotchas)
1. **User-Agent header is mandatory.** Are.na is behind Cloudflare; a default Node/fetch UA can
   get **Error 1010 (Access denied)**. Send a browser-like `User-Agent` on every Are.na fetch,
   exactly like `publish.py` does.
2. **Token is server-side only.** The channel is private → reads need `ARENA_TOKEN`. Fetch only
   from Server Components / Route Handlers / server actions. Set it as a host env var, **never**
   `NEXT_PUBLIC_*`.
3. **`description` is an object** `{markdown, html, plain}`, not a string. Render `description.html`
   directly (it's our own controlled content) — don't re-parse the markdown.
4. **Use the permanent CDN URLs** — `attachment.url` for audio, `image.*.src` for covers. Do not
   proxy them through Next (see cost section).
5. **Cover image is set via the Are.na desktop app**, not the API (the public v3 API can't set a
   block's native cover). Once set, it shows up in `image.src` for the site to pull. One manual
   step per mix.

Suggested: factor "fetch channel + UA header + token" into one small server module the site reuses.

## Example fetch
```js
const res = await fetch("https://api.are.na/v3/channels/fr_20_p_music/contents", {
  headers: {
    Authorization: `Bearer ${process.env.ARENA_TOKEN}`,
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    Accept: "application/json",
  },
  next: { revalidate: 3600 },   // or { tags: ['mixes'] } + revalidateTag('mixes') on publish
});
```

## Staying on Vercel's free tier (no hosting cost)
The real concern is **Vercel's Hobby metering**, not request volume. The cron and revalidate calls are
a **rounding error** — daily cron ≈ 30 tiny function invocations/month, far under any Hobby allowance.
What actually decides whether you stay free is **what flows _through_ Vercel**: keep the heavy bytes on
are.na's CDN and keep pages static. Don't optimize the cron; optimize the byte path.

### Are.na API: cache so visitors never hit it
- The API response is **small JSON** — audio/images are URL *strings*, not payload. So the rate-limit
  concern is about *number of requests*, not size. Goal: don't fetch per visitor.
- **SSG or ISR with a long `revalidate`** (e.g. hourly): one fetch serves all visitors from the edge
  cache. Are.na sees a trickle, not per-view traffic.
- **Best — on-demand revalidation tied to actual block changes** (see next section).

## On-demand revalidation (only call Are.na when blocks actually change)
Goal: rebuild only on the three real change types — **new block**, **cover image upload**,
**tracklist/description edit**. Verified mechanics (2026-06-18):

- **Are.na has NO webhooks.** There is no push from Are.na — any "on-change" scheme is something
  *we* trigger.
- **`channel.updated_at` is NOT a usable signal.** Tested: it stayed at 16:14 while a member block's
  cover (16:20) and description (16:28) were edited. Channel-level `updated_at` only tracks
  channel-metadata changes, so it would miss exactly the cover/tracklist edits we care about.
- **The reliable change signal lives on the blocks.** Compute, across `/contents`:
  `max( block.updated_at, block.image.updated_at )` per block, plus the **block count**
  (catches new/removed connections). Cover uploads bump `image.updated_at`; description/title edits
  bump `block.updated_at`; a new mix bumps both count and max. Store this fingerprint with each build;
  rebuild only when it changes.

Two trigger paths, because two of the three changes happen outside `publish.py`:

1. **`publish.py` push (instant, zero polling)** — for **new blocks** and **tracklist edits** (both
   done *by* the script). After `upload`/`set-meta`, have `publish.py` POST to a Next revalidate
   route with a shared secret → `revalidateTag('mixes')`. The API is hit ~once per publish.
2. **Cover uploads happen in the Are.na desktop app** → nothing to push from. **Chosen approach: a
   once-daily Vercel Cron poll.** It fetches `/contents`, compares the block fingerprint above to the
   last build, and `revalidateTag('mixes')` only if it changed. Covers self-heal within ~24h with no
   manual step. (Manual bookmark to the revalidate route still works any time you want it instant.)

   Why daily and not more often: **Vercel Hobby caps cron at ~once/day (max 2 jobs), best-effort
   timing.** At ≤1 mix/week, daily is plenty — the cron's only job is catching desktop cover uploads,
   since `publish.py` already pushes new mixes + tracklist edits instantly. (Want covers faster while
   staying free? Use an external scheduler — GitHub Actions / cron-job.org — to hit the revalidate
   route, so Vercel isn't running the cron at all.)

Revalidate route (shared by the `publish.py` push and the cron):
```js
// app/api/revalidate/route.ts
export async function POST(req) {
  if (req.headers.get("x-secret") !== process.env.REVALIDATE_SECRET)
    return new Response("nope", { status: 401 });
  revalidateTag("mixes");           // pairs with fetch(..., { next: { tags: ['mixes'] } })
  return Response.json({ revalidated: true });
}
```

Daily cron (Vercel) — fingerprint-compare so it only revalidates on real change:
```json
// vercel.json
{ "crons": [{ "path": "/api/cron/check-mixes", "schedule": "0 6 * * *" }] }
```
```js
// app/api/cron/check-mixes/route.ts  — fetch /contents, compute
//   fingerprint = blockCount + max(block.updated_at, block.image.updated_at)
// compare to the stored last-build fingerprint; if changed -> revalidateTag('mixes') + store it.
```

### Vercel: keep heavy bytes OFF Vercel (the real lever)
Each mix is ~142 MB of audio. If those bytes flowed *through* Vercel, the bandwidth cap blows fast.
They don't have to:

| Asset | Serve via | Why free |
|---|---|---|
| Audio | `<audio src={attachment.url}>` → are.na CDN | Transfer is are.na's bandwidth, never touches Vercel |
| Covers | are.na pre-resized URLs (`image.small.src`/`image.src`) via `<img>` or `next/image` `unoptimized` | Avoids Vercel image-optimization quota; bytes from are.na CDN |
| HTML/CSS/JS | Static pages (SSG/ISR) | Tiny; edge-cached |
| Functions | Only ISR revalidation / rebuilds | Infrequent → negligible |

**The one mistake that costs money:** proxying audio or images through a Next API route or the
`next/image` optimizer. Link straight to the CDN URLs instead.

### Backstops
- Set a **$0 spend limit** in the Vercel dashboard as a hard cap.
- Hobby tier is **non-commercial** only; confirm current Hobby limits when scaffolding (they change).

## Repo layout (when scaffolding)
- `publish.py` + `.claude/` stay at root as ops tooling (stdlib only, zero Node deps — coexists fine).
- Next app under `apps/web/` (or `web/`).
- Do **not** invoke the Python from the Next runtime — the channel is the contract.
