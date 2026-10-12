/**
 * Pure geometry for the decorative globe.
 *
 * Nothing here touches the DOM or WebGL, so it is unit-tested directly. The
 * globe is a visualisation; operational geography (distance, nearest unit) is
 * computed by the backend.
 */

export type Vec3 = [number, number, number];

const DEG = Math.PI / 180;

/** Latitude/longitude in degrees to a point on a sphere (y is north). */
export function latLonToVector(lat: number, lon: number, radius = 1): Vec3 {
  const phi = (90 - lat) * DEG;
  const theta = (lon + 180) * DEG;
  return [
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  ];
}

/** Inverse of `latLonToVector` for a point on any sphere centred at the origin. */
export function vectorToLatLon([x, y, z]: Vec3): { lat: number; lon: number } {
  const r = Math.hypot(x, y, z);
  const lat = 90 - Math.acos(y / r) / DEG;
  let lon = Math.atan2(z, -x) / DEG - 180;
  if (lon < -180) lon += 360;
  return { lat, lon };
}

/**
 * Points along the great circle between two coordinates, lifted off the surface
 * in the middle so the arc reads as an arc. The ends sit exactly on the sphere.
 */
export function greatCircleArc(
  from: { lat: number; lon: number },
  to: { lat: number; lon: number },
  segments = 48,
  lift = 0.18,
  radius = 1,
): Vec3[] {
  const a = latLonToVector(from.lat, from.lon, 1);
  const b = latLonToVector(to.lat, to.lon, 1);
  const dot = Math.min(1, Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const omega = Math.acos(dot);
  const sinOmega = Math.sin(omega);

  const points: Vec3[] = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    // Coincident points have no unique great circle: stay on the spot.
    const wa = sinOmega < 1e-9 ? 1 - t : Math.sin((1 - t) * omega) / sinOmega;
    const wb = sinOmega < 1e-9 ? t : Math.sin(t * omega) / sinOmega;
    const x = wa * a[0] + wb * b[0];
    const y = wa * a[1] + wb * b[1];
    const z = wa * a[2] + wb * b[2];
    const length = Math.hypot(x, y, z) || 1;
    const height = radius + lift * Math.sin(Math.PI * t) * Math.min(1, omega);
    points.push([(x / length) * height, (y / length) * height, (z / length) * height]);
  }
  return points;
}

/** Near-uniform points over a sphere (Fibonacci lattice), as lat/lon degrees. */
export function fibonacciSphere(count: number): { lat: number; lon: number }[] {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const points: { lat: number; lon: number }[] = [];
  for (let i = 0; i < count; i++) {
    const y = 1 - (2 * (i + 0.5)) / count;
    const lat = Math.asin(y) / DEG;
    let lon = ((i * golden) / DEG) % 360;
    if (lon > 180) lon -= 360;
    points.push({ lat, lon });
  }
  return points;
}

/** A land/sea lookup over an equirectangular raster (row 0 is +90° latitude). */
export interface LandMask {
  width: number;
  height: number;
  /** One byte per pixel, non-zero where there is land. */
  data: Uint8Array;
}

export function isLand(mask: LandMask, lat: number, lon: number): boolean {
  const x = Math.min(mask.width - 1, Math.max(0, Math.floor(((lon + 180) / 360) * mask.width)));
  const y = Math.min(mask.height - 1, Math.max(0, Math.floor(((90 - lat) / 180) * mask.height)));
  return (mask.data[y * mask.width + x] ?? 0) > 0;
}

/** The land points to draw, taken from a mask. */
export function landPoints(mask: LandMask, candidates: number, radius = 1): Float32Array {
  const out: number[] = [];
  for (const { lat, lon } of fibonacciSphere(candidates)) {
    if (!isLand(mask, lat, lon)) continue;
    out.push(...latLonToVector(lat, lon, radius));
  }
  return new Float32Array(out);
}
