import { NextResponse, type NextRequest } from "next/server";

import { resolveApiConfig } from "@raksha/api-client/config";
import { contentSecurityPolicy, newNonce } from "@raksha/ui/csp";

/**
 * A fresh Content-Security-Policy nonce for every page request (see
 * `packages/ui/src/csp.ts`). Next.js reads the nonce from the request's CSP header and
 * stamps it on each script it renders; the browser then runs only those.
 */
export function proxy(request: NextRequest) {
  // An unusable API address must not take every page down (the CSP builder parses it),
  // nor quietly become localhost: the page gets no API origin and says why on use.
  const apiConfig = resolveApiConfig({
    value: process.env.NEXT_PUBLIC_API_BASE_URL,
    production: process.env.NODE_ENV === "production",
  });
  const policy = contentSecurityPolicy({
    nonce: newNonce(),
    apiBaseUrl: apiConfig.ok ? apiConfig.baseUrl : undefined,
    tileUrl: process.env.NEXT_PUBLIC_MAP_TILE_URL,
    dev: process.env.NODE_ENV === "development",
  });

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: static assets need no policy, and prefetches are not documents.
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
