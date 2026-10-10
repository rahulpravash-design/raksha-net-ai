import { describe, expect, it } from "vitest";

import type { Hospital } from "@raksha/api-client";

import {
  buildCapacityUpdate,
  capacityAgeHours,
  capacityFormFrom,
  freeShare,
  isCapacityStale,
  isEmptyUpdate,
} from "@/lib/hospital";
import { homeFor, seesIncidents } from "@/lib/routes";

const hospital = {
  id: "h1",
  total_beds: 100,
  available_beds: 12,
  icu_total: 20,
  icu_available: 3,
  accepting_emergencies: true,
  specialties: ["trauma"],
} as Hospital;

describe("capacity freshness", () => {
  const now = Date.parse("2026-01-01T12:00:00Z");
  it("computes age and flags a report older than the threshold", () => {
    expect(capacityAgeHours("2026-01-01T10:00:00Z", now)).toBeCloseTo(2);
    expect(isCapacityStale("2026-01-01T10:00:00Z", now)).toBe(false);
    expect(isCapacityStale("2026-01-01T05:00:00Z", now)).toBe(true);
  });
  it("treats a hospital that has never reported as stale, not as fine", () => {
    expect(isCapacityStale(null, now)).toBe(true);
    expect(capacityAgeHours("garbage", now)).toBeNull();
  });
});

describe("freeShare", () => {
  it("is bounded and safe for zero beds", () => {
    expect(freeShare(12, 100)).toBeCloseTo(0.12);
    expect(freeShare(5, 0)).toBe(0);
    expect(freeShare(500, 100)).toBe(1);
  });
});

describe("buildCapacityUpdate", () => {
  it("sends nothing but the changes", () => {
    const form = { ...capacityFormFrom(hospital), available_beds: "7", accepting_emergencies: false };
    const { errors, input } = buildCapacityUpdate(hospital, form);
    expect(errors).toEqual({});
    expect(input).toEqual({ available_beds: 7, accepting_emergencies: false });
  });

  it("rejects free beds above the total, using the resulting total", () => {
    const form = { ...capacityFormFrom(hospital), total_beds: "10" };
    const { errors, input } = buildCapacityUpdate(hospital, form);
    expect(input).toBeNull();
    expect(errors.available_beds).toMatch(/cannot exceed total/i);
  });

  it("rejects non-numbers, negatives and decimals", () => {
    for (const bad of ["", "abc", "-1", "2.5"]) {
      const { errors } = buildCapacityUpdate(hospital, { ...capacityFormFrom(hospital), icu_available: bad });
      expect(errors.icu_available, bad).toBeDefined();
    }
  });

  it("normalises specialties and carries a note", () => {
    const form = { ...capacityFormFrom(hospital), specialties: "Trauma, burns,  BURNS", note: " shift change " };
    const { input } = buildCapacityUpdate(hospital, form);
    expect(input).toEqual({ specialties: ["trauma", "burns"], note: "shift change" });
  });

  it("recognises an update that changes nothing", () => {
    const { input } = buildCapacityUpdate(hospital, { ...capacityFormFrom(hospital), note: "just checking" });
    expect(isEmptyUpdate(input!)).toBe(true);
  });
});

describe("homeFor", () => {
  it("sends a hospital operator to hospitals, and nobody else", () => {
    expect(homeFor("HOSPITAL_OPERATOR")).toBe("/hospitals");
    expect(homeFor("DISPATCHER")).toBe("/dashboard");
    expect(seesIncidents("HOSPITAL_OPERATOR")).toBe(false);
    expect(seesIncidents("RESPONDER")).toBe(true);
  });
});
