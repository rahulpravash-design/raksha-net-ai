import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The shared client ships as TypeScript source, so Next compiles it with the app.
  transpilePackages: ["@raksha/api-client", "@raksha/ui"],
  // Standalone output keeps the production image small (see docs/DEPLOYMENT.md).
  output: "standalone",
  outputFileTracingRoot: new URL("../../", import.meta.url).pathname,
  // The Content-Security-Policy is set per request, with a nonce, in proxy.ts.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
