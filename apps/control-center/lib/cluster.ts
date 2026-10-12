import type { PriorityBand } from "@raksha/api-client";

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  band: PriorityBand | null;
}

export interface Cluster {
  /** Stable across renders for the same membership. */
  key: string;
  lat: number;
  lon: number;
  count: number;
  /** Most urgent band among the members, so a cluster never hides a critical one. */
  band: PriorityBand | null;
  ids: string[];
}

const URGENCY: Record<PriorityBand, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

export function moreUrgent(a: PriorityBand | null, b: PriorityBand | null): PriorityBand | null {
  const score = (band: PriorityBand | null) => (band ? URGENCY[band] : 0);
  return score(b) > score(a) ? b : a;
}

/**
 * Group points that would land within `cellPx` of each other on screen at this
 * zoom. A simple grid is enough at pilot scale (the API returns a bounded
 * viewport feed) and has no dependency; clusters dissolve as the operator zooms.
 */
export function clusterPoints(points: MapPoint[], zoom: number, cellPx = 56): Cluster[] {
  const degreesPerPixel = 360 / (256 * 2 ** zoom);
  const cell = cellPx * degreesPerPixel;
  const cells = new Map<string, MapPoint[]>();
  for (const point of points) {
    const key = `${Math.floor(point.lon / cell)}:${Math.floor(point.lat / cell)}`;
    const bucket = cells.get(key);
    if (bucket) bucket.push(point);
    else cells.set(key, [point]);
  }

  return [...cells.values()].map((members) => {
    const lat = members.reduce((sum, m) => sum + m.lat, 0) / members.length;
    const lon = members.reduce((sum, m) => sum + m.lon, 0) / members.length;
    const band = members.reduce<PriorityBand | null>((top, m) => moreUrgent(top, m.band), null);
    const ids = members.map((m) => m.id).sort();
    return { key: ids.join("|"), lat, lon, count: members.length, band, ids };
  });
}
