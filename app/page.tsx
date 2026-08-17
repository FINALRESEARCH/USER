import { fetchMixes } from "@/lib/arena";
import MixItem from "@/components/Mix";
import PermalinkOpener from "@/components/PermalinkOpener";

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
      <PermalinkOpener />
      {mixes.length === 0 ? (
        <p>No mixes yet.</p>
      ) : (
        // Sequential, display-order numbers (#1 = newest) so a mix can be
        // linked as yoursite.com/#1. Note: this number shifts for every mix
        // when a new one is published, so old #N links can later point at a
        // different mix — accepted tradeoff, see CLAUDE.md/WEBAPP.md.
        mixes.map((mix, i) => <MixItem key={mix.id} mix={mix} number={i + 1} />)
      )}
    </main>
  );
}
