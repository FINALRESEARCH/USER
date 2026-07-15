import { fetchMixes } from "@/lib/arena";
import MixItem from "@/components/Mix";
import FinalResearchCredit from "@/components/FinalResearchCredit";

// Statically rendered, revalidated by the 'mixes' tag (see lib/arena.ts).
// Visitors hit the edge cache; Are.na sees a trickle, not per-view traffic.
export default async function Home() {
  let mixes;
  try {
    mixes = await fetchMixes();
  } catch (err) {
    return (
      <main>
        <h1>USER</h1>
        <FinalResearchCredit />
        <p>Could not load mixes: {(err as Error).message}</p>
      </main>
    );
  }

  return (
    <main>
      <h1>USER</h1>
      <FinalResearchCredit />
      {mixes.length === 0 ? (
        <p>No mixes yet.</p>
      ) : (
        mixes.map((mix) => <MixItem key={mix.id} mix={mix} />)
      )}
    </main>
  );
}
