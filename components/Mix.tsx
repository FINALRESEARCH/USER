import type { Mix } from "@/lib/arena";
import AudioPlayer from "@/components/AudioPlayer";

// One published mix. Render order (per design): title → audio → tracklist → cover.
export default function MixItem({ mix }: { mix: Mix }) {
  return (
    <div>
      <h2>{mix.title}</h2>

      {/* Stream straight from the are.na CDN — never proxied through Next. */}
      {mix.audioUrl ? <AudioPlayer src={mix.audioUrl} /> : null}

      {mix.descriptionHtml || mix.coverSmall ? (
        <details>
          <summary>View Details</summary>
          {/* description.html is our own controlled content from publish.py —
              anchors already carry target/rel. Render it directly. */}
          {mix.descriptionHtml ? (
            <div dangerouslySetInnerHTML={{ __html: mix.descriptionHtml }} />
          ) : null}
          {/* Cover lives inside the tracklist — only shown when expanded. */}
          {mix.coverSmall ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={mix.coverSmall} alt={`${mix.title} cover`} />
          ) : null}
        </details>
      ) : null}
    </div>
  );
}
