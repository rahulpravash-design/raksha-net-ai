import { describe, expect, it } from "vitest";

import {
  BAND_STYLES,
  bandStyle,
  canDispatch,
  categoryLabel,
  citizenStatusMessage,
  formatBytes,
  formatCoordinates,
  formatRelative,
  isOperationalRole,
  INCIDENT_CATEGORIES,
  INCIDENT_STATUSES,
  statusLabel,
  USER_ROLES,
} from "@raksha/api-client";

describe("priority presentation", () => {
  it("gives every band a distinct colour and its own text label", () => {
    const markers = Object.values(BAND_STYLES).map((style) => style.marker);
    expect(new Set(markers).size).toBe(markers.length);

    // Colour is never the only signal — each band carries readable text too.
    for (const style of Object.values(BAND_STYLES)) {
      expect(style.label.trim().length).toBeGreaterThan(0);
    }
  });

  it("falls back to a neutral style for an unscored incident", () => {
    expect(bandStyle(null).label).toBe("Not scored");
  });

  it("styles a critical incident in red", () => {
    expect(bandStyle("CRITICAL").marker).toBe("#dc2626");
  });
});

describe("labels", () => {
  it("labels every incident category", () => {
    for (const category of INCIDENT_CATEGORIES) {
      expect(categoryLabel(category)).not.toBe(category);
    }
  });

  it("labels every status", () => {
    for (const status of INCIDENT_STATUSES) {
      expect(statusLabel(status)).toBeTruthy();
    }
  });

  it("gives the reporter plain language for every status", () => {
    for (const status of INCIDENT_STATUSES) {
      const message = citizenStatusMessage(status);
      expect(message.length).toBeGreaterThan(10);
      // The reporter should never be shown a raw enum name.
      expect(message).not.toContain("_");
    }
  });
});

describe("roles", () => {
  it("treats a citizen as neither operational nor a dispatcher", () => {
    expect(isOperationalRole("CITIZEN")).toBe(false);
    expect(canDispatch("CITIZEN")).toBe(false);
  });

  it("lets a dispatcher and above dispatch", () => {
    expect(canDispatch("DISPATCHER")).toBe(true);
    expect(canDispatch("ADMIN")).toBe(true);
    expect(canDispatch("SUPER_ADMIN")).toBe(true);
  });

  it("lets a responder see incidents without dispatching", () => {
    expect(isOperationalRole("RESPONDER")).toBe(true);
    expect(canDispatch("RESPONDER")).toBe(false);
  });

  it("classifies every known role", () => {
    for (const role of USER_ROLES) {
      expect(typeof isOperationalRole(role)).toBe("boolean");
    }
  });
});

describe("formatting", () => {
  const now = new Date("2026-01-01T12:00:00Z");

  it.each([
    ["2026-01-01T11:59:30Z", "30s ago"],
    ["2026-01-01T11:45:00Z", "15 min ago"],
    ["2026-01-01T09:30:00Z", "2 h 30 min ago"],
    ["2025-12-31T12:00:00Z", "1 day ago"],
    ["2025-12-29T12:00:00Z", "3 days ago"],
  ])("renders %s as %s", (iso, expected) => {
    expect(formatRelative(iso, now)).toBe(expected);
  });

  it("does not render a future timestamp as negative", () => {
    expect(formatRelative("2026-01-01T12:05:00Z", now)).toBe("just now");
  });

  it("handles an unparseable timestamp without throwing", () => {
    expect(formatRelative("not a date", now)).toBe("—");
  });

  it("renders coordinates to five decimal places", () => {
    expect(formatCoordinates("13.0827", "80.2707")).toBe("13.08270, 80.27070");
  });

  it("renders coordinates supplied as numbers", () => {
    expect(formatCoordinates(13.0827, 80.2707)).toBe("13.08270, 80.27070");
  });

  it("returns a placeholder for unusable coordinates", () => {
    expect(formatCoordinates("north", "80.2")).toBe("—");
  });

  it.each([
    [512, "512 B"],
    [2048, "2 KB"],
    [5 * 1024 * 1024, "5.0 MB"],
  ])("renders %d bytes as %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});
