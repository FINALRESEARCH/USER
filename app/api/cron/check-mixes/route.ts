import { revalidateTag } from "next/cache";
import { fetchFingerprint } from "@/lib/arena";

// Daily Vercel cron (see vercel.json). Catches changes that happen OUTSIDE
// publish.py — chiefly cover uploads done in the Are.na desktop app. publish.py
// already pushes new mixes + tracklist edits instantly via /api/revalidate.
//
// Are.na has no webhooks and channel.updated_at is unreliable, so we fingerprint
// the blocks (see lib/arena.ts) and only revalidate when the fingerprint changes.
//
// NOTE (scaffold): the "last seen" fingerprint is not yet persisted across
// invocations — durable storage (e.g. Vercel KV) is a follow-up. Until then this
// route revalidates on every run, which is harmless at ≤1 cron/day. Wire up KV to
// make it a true change-only trigger.
export async function GET() {
  let fingerprint: string;
  try {
    fingerprint = await fetchFingerprint();
  } catch (err) {
    return Response.json(
      { ok: false, error: (err as Error).message },
      { status: 500 }
    );
  }

  // TODO: read lastFingerprint from durable storage; bail if unchanged; store new.
  revalidateTag("mixes", "max");
  return Response.json({ revalidated: true, fingerprint });
}
