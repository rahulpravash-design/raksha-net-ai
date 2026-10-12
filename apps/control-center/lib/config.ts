/**
 * Front-end configuration.
 *
 * Every value here is a build-time public value. Nothing secret belongs in a
 * `NEXT_PUBLIC_` variable — it is compiled into the bundle the browser downloads.
 */

import { resolveApiConfig } from "@raksha/api-client";

/**
 * The API address, validated. A production build with it unset, malformed or still the
 * `.invalid` placeholder yields `ok: false` and a message for the site owner; there is
 * deliberately no fallback to localhost outside development (see
 * `packages/api-client/src/config.ts`). `process.env.NEXT_PUBLIC_API_BASE_URL` must be
 * written out in full here: Next.js only inlines that exact expression.
 */
export const API_CONFIG = resolveApiConfig({
  value: process.env.NEXT_PUBLIC_API_BASE_URL,
  production: process.env.NODE_ENV === "production",
});

export const MAP_DEFAULTS = {
  centre: {
    latitude: Number(process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT ?? 13.0827),
    longitude: Number(process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER_LON ?? 80.2707),
  },
  zoom: Number(process.env.NEXT_PUBLIC_DEFAULT_MAP_ZOOM ?? 11),
};

export const MAP_TILES = {
  url:
    process.env.NEXT_PUBLIC_MAP_TILE_URL ??
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution:
    process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ??
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
};

/**
 * Where "Report an emergency" leads. The citizen application is a separate
 * deployable, so this is its public address, not a route in this app.
 */
export const CITIZEN_APP_URL: string | undefined =
  process.env.NEXT_PUBLIC_CITIZEN_APP_URL?.trim() ||
  // Only a development build may guess. In production a guess would send every visitor
  // to *their own* localhost, so an unset value means "not linked" and the page says so.
  (process.env.NODE_ENV === "production" ? undefined : "http://localhost:3000");
