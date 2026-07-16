import { revalidateTag } from "next/cache";

// Shared by the publish.py push (new mixes + tracklist edits) and the daily cron.
// POST with header x-secret: <REVALIDATE_SECRET>.
export async function POST(req: Request) {
  const expected = process.env.REVALIDATE_SECRET?.trim();
  const received = req.headers.get("x-secret")?.trim();
  if (!expected) {
    // Distinguish "not configured on the server" from "wrong value" without
    // ever echoing the secret itself — this case looks identical otherwise.
    return Response.json(
      { revalidated: false, reason: "REVALIDATE_SECRET is not set in this deployment's environment" },
      { status: 401 }
    );
  }
  if (received !== expected) {
    return Response.json({ revalidated: false, reason: "secret mismatch" }, { status: 401 });
  }
  revalidateTag("mixes", "max");
  return Response.json({ revalidated: true });
}
