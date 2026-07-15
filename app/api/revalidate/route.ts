import { revalidateTag } from "next/cache";

// Shared by the publish.py push (new mixes + tracklist edits) and the daily cron.
// POST with header x-secret: <REVALIDATE_SECRET>.
export async function POST(req: Request) {
  if (req.headers.get("x-secret") !== process.env.REVALIDATE_SECRET) {
    return new Response("nope", { status: 401 });
  }
  revalidateTag("mixes", "max");
  return Response.json({ revalidated: true });
}
