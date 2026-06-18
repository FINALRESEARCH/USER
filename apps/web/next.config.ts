import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // We render covers with plain <img> straight from the are.na CDN, so the
  // Next image optimizer never runs. Keeping this unoptimized is the whole
  // point: heavy bytes stay on are.na's CDN, never billed through Vercel.
  images: { unoptimized: true },
};

export default nextConfig;
