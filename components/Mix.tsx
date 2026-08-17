import type { Mix } from "@/lib/arena";
import AudioPlayer from "@/components/AudioPlayer";

// One published mix. Render order (per design): title → audio → tracklist → cover.
//
// `number` is this mix's position in the displayed list (#1 = newest) and
// doubles as its permalink fragment: yoursite.com/#1 opens the page scrolled
// to this mix with its tracklist expanded (see PermalinkOpener).
export default function MixItem({ mix, number }: { mix: Mix; number: number }) {
  return (
    <div className="mix" id={String(number)}>
      <h2>{mix.title}</h2>

      {/* Stream straight from the are.na CDN — never proxied through Next. */}
      {mix.audioUrl ? <AudioPlayer src={mix.audioUrl} /> : null}

      {mix.descriptionHtml || mix.coverFull ? (
        <details>
          <summary>View Details</summary>
          {/* description.html is our own controlled content from publish.py —
              anchors already carry target/rel. Render it directly. */}
          {mix.descriptionHtml ? (
            <div className="tracklist" dangerouslySetInnerHTML={{ __html: mix.descriptionHtml }} />
          ) : null}
          {/* Cover lives inside the tracklist — only shown when expanded.
              Full-res source even though CSS displays it small (img{max-width:240px}
              in globals.css): the pre-resized `small` variant (400px) reads blurry
              once the browser scales it up for a 2x/3x display. Bytes still come
              straight from are.na's CDN either way, so this doesn't touch Vercel. */}
          {mix.coverFull ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mix.coverFull} alt={`${mix.title} cover`} />
          ) : null}
        </details>
      ) : null}
    </div>
  );
}
