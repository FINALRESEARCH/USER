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

  // Permalink numbers follow publish order (oldest = #1), matching the "USER N"
  // title convention — NOT display order (mixes render newest-first, above).
  // Ranking by position instead of by title text means it still works if a
  // mix is ever retitled, and — unlike numbering by display position — a
  // mix's number never shifts when a newer mix is published.
  const numberByMixId = new Map(
    [...mixes].sort((a, b) => a.position - b.position).map((mix, i) => [mix.id, i + 1])
  );

  return (
    <main>
      <PermalinkOpener />
      {mixes.length === 0 ? (
        <p>No mixes yet.</p>
      ) : (
        mixes.map((mix) => (
          <MixItem key={mix.id} mix={mix} number={numberByMixId.get(mix.id)!} />
        ))
      )}
    </main>
  );
}
