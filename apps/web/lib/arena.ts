// The single read module: fetch the published-mixes channel from Are.na.
//
// Read-side contracts (see ../../WEBAPP.md and root CLAUDE.md — learned the hard way):
//  1. User-Agent is MANDATORY. Are.na sits behind Cloudflare; a default Node/fetch
//     UA gets Error 1010 (Access denied). Always send a browser-like UA.
//  2. ARENA_TOKEN is SERVER-ONLY (private channel). This module must only ever run
//     on the server (Server Components / Route Handlers) — never bundle it client-side.
//  3. `description` comes back as an OBJECT { markdown, html, plain }, not a string.
//     Render description.html directly (our own controlled content with real anchors).
//  4. Audio/cover are CDN URL strings (attachment.url, image.*.src). Link straight to
//     them — never proxy through Next — so the bytes stay on are.na's CDN.

const API_BASE = process.env.ARENA_API_BASE || "https://api.are.na/v3";

// Same browser UA publish.py uses, to clear Cloudflare.
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36";

export type Mix = {
  id: number;
  title: string;
  audioUrl: string | null;
  coverSmall: string | null;
  coverFull: string | null;
  descriptionHtml: string;
  connectionId: number | null;
  position: number;
  updatedAt: string | null;
  imageUpdatedAt: string | null;
};

type ArenaImage = {
  src?: string;
  small?: { src?: string };
  updated_at?: string;
};

type ArenaBlock = {
  id: number;
  class?: string;
  title?: string | null;
  attachment?: { url?: string } | null;
  image?: ArenaImage | null;
  description?: { html?: string } | string | null;
  connection?: { id?: number; position?: number } | null;
  updated_at?: string | null;
};

// v3 returns the channel's blocks under `data` (with a `meta` page wrapper).
type ContentsResponse = { data?: ArenaBlock[] };

async function fetchContents(): Promise<ArenaBlock[]> {
  const channel = process.env.ARENA_CHANNEL;
  const token = process.env.ARENA_TOKEN;
  if (!channel) throw new Error("ARENA_CHANNEL is not set");
  if (!token) throw new Error("ARENA_TOKEN is not set");

  const res = await fetch(`${API_BASE}/channels/${channel}/contents`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "User-Agent": USER_AGENT,
      Accept: "application/json",
    },
    // One fetch serves all visitors from the edge cache. Revalidated on demand
    // via revalidateTag('mixes') (publish.py push + daily cron).
    next: { tags: ["mixes"] },
  });

  if (!res.ok) {
    throw new Error(`Are.na fetch failed: ${res.status} ${res.statusText}`);
  }
  const data = (await res.json()) as ContentsResponse;
  return data.data ?? [];
}

function descriptionHtml(d: ArenaBlock["description"]): string {
  if (!d) return "";
  if (typeof d === "string") return d;
  return d.html ?? "";
}

export async function fetchMixes(): Promise<Mix[]> {
  const blocks = await fetchContents();
  return blocks
    // One Attachment block = one mix.
    .filter((b) => b.class === "Attachment" || b.attachment?.url)
    .map((b) => ({
      id: b.id,
      title: b.title?.trim() || "Untitled",
      audioUrl: b.attachment?.url ?? null,
      coverSmall: b.image?.small?.src ?? null,
      coverFull: b.image?.src ?? null,
      descriptionHtml: descriptionHtml(b.description),
      connectionId: b.connection?.id ?? null,
      position: b.connection?.position ?? 0,
      updatedAt: b.updated_at ?? null,
      imageUpdatedAt: b.image?.updated_at ?? null,
    }))
    // Newest first.
    .sort((a, b) => b.position - a.position);
}

// Change signal for the cron: channel.updated_at is unreliable (it misses cover
// and description edits), so fingerprint the blocks. blockCount catches new/removed
// mixes; max(updated_at, image.updated_at) catches tracklist + cover edits.
export async function fetchFingerprint(): Promise<string> {
  const mixes = await fetchMixes();
  let max = "";
  for (const m of mixes) {
    if (m.updatedAt && m.updatedAt > max) max = m.updatedAt;
    if (m.imageUpdatedAt && m.imageUpdatedAt > max) max = m.imageUpdatedAt;
  }
  return `${mixes.length}:${max}`;
}
