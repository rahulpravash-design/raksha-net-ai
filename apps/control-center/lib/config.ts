/**
 * Front-end configuration.
 *
 * Every value here is a build-time public value. Nothing secret belongs in a
 * `NEXT_PUBLIC_` variable — it is compiled into the bundle the browser downloads.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
