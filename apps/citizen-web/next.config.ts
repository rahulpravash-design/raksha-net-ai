import type { NextConfig } from "next";

/**
 * Content-Security-Policy. The only origins the browser may talk to are the API
 * and the map tile host; everything else is refused.
 *
 * 'unsafe-inline' is allowed for scripts and styles: Next.js emits inline
 * bootstrap scripts and Tailwind/Leaflet set inline styles, and removing it
 * needs per-request nonces (see docs/SECURITY.md section 6 for the tradeoff).
 * 'unsafe-eval' is development-only, for React's refresh runtime.
 */
function contentSecurityPolicy(): string {
  const apiOrigin = new URL(
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  ).origin;
  const tileOrigin = new URL(
    (
      process.env.NEXT_PUBLIC_MAP_TILE_URL ??
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    ).replace("{s}", "*"),
  ).origin;
  const dev = process.env.NODE_ENV === "development";

  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${tileOrigin}`,
    "font-src 'self' data:",
    `connect-src 'self' ${apiOrigin}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The shared client ships as TypeScript source, so Next compiles it with the app.
  transpilePackages: ["@raksha/api-client", "@raksha/ui"],
  // Standalone output keeps the production image small (see docs/DEPLOYMENT.md).
  output: "standalone",
  outputFileTracingRoot: new URL("../../", import.meta.url).pathname,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Content-Security-Policy", value: contentSecurityPolicy() },
        ],
      },
    ];
  },
};

export default nextConfig;
