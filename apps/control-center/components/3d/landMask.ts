import type { Topology } from "topojson-specification";
import { feature } from "topojson-client";
import land from "world-atlas/land-110m.json";

import type { LandMask } from "@/lib/globe";

const WIDTH = 720;
const HEIGHT = 360;

/**
 * Rasterise Natural Earth 1:110m land (public domain, via `world-atlas`) into an
 * equirectangular mask, so the globe's land is real coastline rather than noise.
 * Needs a 2D canvas, so it runs in the browser only; returns null where one is
 * unavailable and the caller draws no land rather than a made-up planet.
 */
export function buildLandMask(): LandMask | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;

  const topology = land as unknown as Topology;
  const collection = feature(topology, topology.objects.land as never) as unknown as {
    features?: { geometry: Geometry }[];
    geometry?: Geometry;
  };
  const geometries: Geometry[] = collection.features
    ? collection.features.map((f) => f.geometry)
    : collection.geometry
      ? [collection.geometry]
      : [];

  context.fillStyle = "#fff";
  const project = ([lon, lat]: number[]): [number, number] => [
    ((lon! + 180) / 360) * WIDTH,
    ((90 - lat!) / 180) * HEIGHT,
  ];

  for (const geometry of geometries) {
    const polygons =
      geometry.type === "Polygon"
        ? [geometry.coordinates as number[][][]]
        : (geometry.coordinates as number[][][][]);
    for (const polygon of polygons) {
      context.beginPath();
      for (const ring of polygon) {
        ring.forEach((position, index) => {
          const [x, y] = project(position);
          if (index === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        context.closePath();
      }
      context.fill("evenodd");
    }
  }

  const { data } = context.getImageData(0, 0, WIDTH, HEIGHT);
  const mask = new Uint8Array(WIDTH * HEIGHT);
  for (let i = 0; i < mask.length; i++) mask[i] = data[i * 4 + 3] ?? 0;
  return { width: WIDTH, height: HEIGHT, data: mask };
}

interface Geometry {
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown;
}
