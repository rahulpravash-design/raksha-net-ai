import { describe, expect, it } from "vitest";

import { clusterPoints, moreUrgent, type MapPoint } from "@/lib/cluster";

const p = (id: string, lat: number, lon: number, band: MapPoint["band"] = "LOW"): MapPoint => ({
  id,
  lat,
  lon,
  band,
});

describe("clusterPoints", () => {
  it("keeps distant points separate", () => {
    const out = clusterPoints([p("a", 13.0, 80.0), p("b", 28.6, 77.2)], 10);
    expect(out).toHaveLength(2);
    expect(out.every((c) => c.count === 1)).toBe(true);
  });

  it("merges nearby points at a low zoom and splits them when zoomed in", () => {
    const pts = [p("a", 13.0, 80.0), p("b", 13.01, 80.01), p("c", 13.02, 80.0)];
    const far = clusterPoints(pts, 8);
    expect(far).toHaveLength(1);
    expect(far[0]!.count).toBe(3);
    const near = clusterPoints(pts, 18);
    expect(near).toHaveLength(3);
  });

  it("never hides the most urgent member of a cluster", () => {
    const out = clusterPoints(
      [p("a", 13.0, 80.0, "LOW"), p("b", 13.001, 80.001, "CRITICAL"), p("c", 13.002, 80.0, null)],
      6,
    );
    expect(out).toHaveLength(1);
    expect(out[0]!.band).toBe("CRITICAL");
  });

  it("accounts for every point exactly once", () => {
    const pts = Array.from({ length: 50 }, (_, i) => p(`p${i}`, 12 + (i % 7) * 0.05, 79 + (i % 5) * 0.05));
    const out = clusterPoints(pts, 11);
    expect(out.flatMap((c) => c.ids).sort()).toEqual(pts.map((x) => x.id).sort());
  });

  it("handles an empty feed", () => {
    expect(clusterPoints([], 10)).toEqual([]);
  });
});

describe("moreUrgent", () => {
  it("orders bands, treating unscored as least urgent", () => {
    expect(moreUrgent("LOW", "HIGH")).toBe("HIGH");
    expect(moreUrgent("HIGH", "MEDIUM")).toBe("HIGH");
    expect(moreUrgent(null, "LOW")).toBe("LOW");
    expect(moreUrgent("LOW", null)).toBe("LOW");
  });
});
