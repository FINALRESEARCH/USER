"use client";

import { useEffect } from "react";

// Mix wrappers carry a plain numeric id (see components/Mix.tsx), so
// yoursite.com/#1 lands on the right element via the browser's native
// fragment scroll — but the tracklist is inside a collapsed <details>, which
// the browser won't open on its own. This opens it and re-does the scroll
// (native scroll happens before the <details> expands, which can leave it
// mis-positioned once the content's height changes).
export default function PermalinkOpener() {
  useEffect(() => {
    function openFromHash() {
      const hash = window.location.hash.slice(1);
      if (!hash) return;
      const el = document.getElementById(hash);
      if (!el) return;
      const details = el.querySelector("details");
      if (details) details.open = true;
      el.scrollIntoView({ block: "start" });
    }
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, []);

  return null;
}
