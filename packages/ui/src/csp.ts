/**
 * The front ends' Content-Security-Policy, built per request with a fresh nonce.
 *
 * Scripts: only those carrying this request's nonce run (`'strict-dynamic'` lets them
 * load the rest of the bundle). There is no `'unsafe-inline'`, so an injected
 * `<script>` or `onerror=` attribute does not execute — the property the old static
 * policy could not give. Next.js reads the nonce from the request's CSP header and
 * puts it on every script it emits; that needs per-request rendering, which each
 * app's root layout asks for.
 *
 * Styles keep `'unsafe-inline'`: React renders `style` props as HTML attributes
 * (motion, Leaflet and the map set them too), and a nonce cannot cover an attribute.
 * Style injection can restyle a page but cannot run code, so this is the accepted
 * remainder (docs/SECURITY.md section 6).
 *
 * Kept free of React and Node-only APIs: it runs in each app's `proxy.ts`.
 */

export interface CspOptions {
  nonce: string;
  /** The API's base URL: the only origin besides this one the page may call. */
  apiBaseUrl: string;
  /** A map tile URL template (`{s}` allowed); its origin may serve images. */
  tileUrl?: string | undefined;
  /** Development adds `'unsafe-eval'` for React's debugging aids; production never does. */
  dev: boolean;
}

const DEFAULT_TILES = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

/** 128 random bits, base64. Unpredictable and unique per request. */
export function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

export function contentSecurityPolicy({ nonce, apiBaseUrl, tileUrl, dev }: CspOptions): string {
  const apiOrigin = new URL(apiBaseUrl).origin;
  const tileOrigin = new URL((tileUrl ?? DEFAULT_TILES).replace("{s}", "*")).origin;
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
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
