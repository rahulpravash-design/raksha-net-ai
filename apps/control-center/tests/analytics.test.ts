import { describe, expect, it } from "vitest";

import { barShare, cellSizeKm, formatMinutes, isSmallSample, sinceFor } from "@/lib/analytics";

describe("sinceFor", () => {
  const now = Date.parse("2026-01-10T12:00:00Z");
  it("computes the lower bound for each period", () => {
    expect(sinceFor("24h", now)).toBe("2026-01-09T12:00:00.000Z");
    expect(sinceFor("7d", now)).toBe("2026-01-03T12:00:00.000Z");
    expect(sinceFor("30d", now)).toBe("2025-12-11T12:00:00.000Z");
  });
  it("sends no bound for all time", () => {
    expect(sinceFor("all", now)).toBeUndefined();
  });
});

describe("formatMinutes", () => {
  it("is readable at every scale and never invents a value", () => {
    expect(formatMinutes(null)).toBe("—");
    expect(formatMinutes(0.4)).toBe("under a minute");
    expect(formatMinutes(12.4)).toBe("12 min");
    expect(formatMinutes(60)).toBe("1 h");
    expect(formatMinutes(75)).toBe("1 h 15 min");
    expect(formatMinutes(Number.NaN)).toBe("—");
  });
});

describe("isSmallSample", () => {
  it("flags 1–4 cases, not zero (that is 'no data') and not five", () => {
    expect(isSmallSample(0)).toBe(false);
    expect(isSmallSample(1)).toBe(true);
    expect(isSmallSample(4)).toBe(true);
    expect(isSmallSample(5)).toBe(false);
  });
});

describe("barShare", () => {
  it("scales to the maximum and survives empty data", () => {
    expect(barShare(5, 10)).toBe(0.5);
    expect(barShare(0, 10)).toBe(0);
    expect(barShare(3, 0)).toBe(0);
    expect(barShare(30, 10)).toBe(1);
  });
});

describe("cellSizeKm", () => {
  it("turns degrees into kilometres", () => {
    expect(cellSizeKm(0.01)).toBe(1.1);
  });
});
