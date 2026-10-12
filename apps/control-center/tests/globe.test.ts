import { describe, expect, it } from "vitest";

import {
  fibonacciSphere,
  greatCircleArc,
  isLand,
  landPoints,
  latLonToVector,
  vectorToLatLon,
} from "@/lib/globe";

describe("latLonToVector", () => {
  it("puts the poles on the y axis and stays on the sphere", () => {
    const [x, y, z] = latLonToVector(90, 0, 2);
    expect(y).toBeCloseTo(2);
    expect(Math.hypot(x, z)).toBeCloseTo(0);
    expect(latLonToVector(-90, 0)[1]).toBeCloseTo(-1);
    const p = latLonToVector(13.08, 80.27, 1.5);
    expect(Math.hypot(...p)).toBeCloseTo(1.5);
  });

  it("round-trips through vectorToLatLon", () => {
    for (const [lat, lon] of [
      [13.0827, 80.2707],
      [-33.9, 151.2],
      [64.1, -21.9],
      [0, 179.5],
    ] as const) {
      const back = vectorToLatLon(latLonToVector(lat, lon));
      expect(back.lat).toBeCloseTo(lat, 6);
      expect(back.lon).toBeCloseTo(lon, 6);
    }
  });
});

describe("greatCircleArc", () => {
  const delhi = { lat: 28.6139, lon: 77.209 };
  const chennai = { lat: 13.0827, lon: 80.2707 };

  it("starts and ends exactly on the two coordinates, on the surface", () => {
    const arc = greatCircleArc(delhi, chennai, 32, 0.2);
    expect(arc).toHaveLength(33);
    const start = vectorToLatLon(arc[0]!);
    const end = vectorToLatLon(arc[32]!);
    expect(start.lat).toBeCloseTo(delhi.lat, 6);
    expect(end.lon).toBeCloseTo(chennai.lon, 6);
    expect(Math.hypot(...arc[0]!)).toBeCloseTo(1);
    expect(Math.hypot(...arc[32]!)).toBeCloseTo(1);
  });

  it("rises above the surface in the middle", () => {
    const arc = greatCircleArc(delhi, chennai, 32, 0.2);
    expect(Math.hypot(...arc[16]!)).toBeGreaterThan(1.01);
  });

  it("does not produce NaN for identical or antipodal points", () => {
    const same = greatCircleArc(delhi, delhi, 8);
    const anti = greatCircleArc({ lat: 0, lon: 0 }, { lat: 0, lon: 180 }, 8);
    for (const p of [...same, ...anti]) {
      expect(p.every(Number.isFinite)).toBe(true);
    }
  });
});

describe("land mask", () => {
  const width = 8;
  const height = 4;
  // West hemisphere (left half) is land, east is sea.
  const data = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) for (let x = 0; x < width / 2; x++) data[y * width + x] = 255;
  const mask = { width, height, data };

  it("looks up land by coordinate", () => {
    expect(isLand(mask, 10, -90)).toBe(true);
    expect(isLand(mask, 10, 90)).toBe(false);
    expect(isLand(mask, 90, -180)).toBe(true);
    expect(isLand(mask, -90, 180)).toBe(false);
  });

  it("keeps only land points", () => {
    const pts = landPoints(mask, 2000);
    expect(pts.length % 3).toBe(0);
    expect(pts.length / 3).toBeGreaterThan(500);
    expect(pts.length / 3).toBeLessThan(1500);
  });
});

describe("fibonacciSphere", () => {
  it("returns the requested number of valid coordinates", () => {
    const pts = fibonacciSphere(500);
    expect(pts).toHaveLength(500);
    expect(pts.every((p) => Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180)).toBe(true);
  });
});
