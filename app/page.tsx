import { fetchMixes } from "@/lib/arena";
import MixItem from "@/components/Mix";

// Statically rendered, revalidated by the 'mixes' tag (see lib/arena.ts).
// Visitors hit the edge cache; Are.na sees a trickle, not per-view traffic.
//
// The on-page "USER" heading and the FinalResearchCredit line are hidden for
// now (not deleted — components/FinalResearchCredit.tsx is still there if
// this gets reversed later).
export default async function Home() {
  let mixes;
  try {
    mixes = await fetchMixes();
  } catch (err) {
    return (
      <main>
        <p>Could not load mixes: {(err as Error).message}</p>
      </main>
    );
  }

  return (
    <main>
      {mixes.length === 0 ? (
        <p>No mixes yet.</p>
      ) : (
        mixes.map((mix) => <MixItem key={mix.id} mix={mix} />)
      )}
    </main>
  );
}
