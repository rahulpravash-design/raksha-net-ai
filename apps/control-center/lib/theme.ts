import type { PriorityBand, ResourceStatus } from "@raksha/api-client";

/**
 * Priority colours for the map and the 3D scenes (the DOM uses Tailwind
 * classes from api-client). Each band also has a glyph and a text label, so
 * priority is never conveyed by colour alone.
 */
export const PRIORITY_THEME: Record<
  PriorityBand | "NONE",
  { hex: string; label: string; glyph: string }
> = {
  CRITICAL: { hex: "#ff354d", label: "Critical", glyph: "▲" },
  HIGH: { hex: "#ff8a3d", label: "High", glyph: "◆" },
  MEDIUM: { hex: "#ffd166", label: "Medium", glyph: "■" },
  LOW: { hex: "#38d996", label: "Low", glyph: "●" },
  NONE: { hex: "#91a4bd", label: "Not scored", glyph: "○" },
};

export function priorityTheme(band: PriorityBand | null) {
  return PRIORITY_THEME[band ?? "NONE"];
}

export const COLORS = {
  void: "#050914",
  deep: "#0a1220",
  panel: "#0e192a",
  cyan: "#00e5ff",
  blue: "#3285ff",
} as const;

/** Border/label colour per resource status on the map. Dashed border marks out-of-service. */
export const RESOURCE_STATUS_COLOR: Record<ResourceStatus, string> = {
  AVAILABLE: "#00e5ff",
  DISPATCHED: "#3285ff",
  EN_ROUTE: "#3285ff",
  ON_SCENE: "#3285ff",
  OUT_OF_SERVICE: "#91a4bd",
};
