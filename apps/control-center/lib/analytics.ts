export type PeriodKey = "24h" | "7d" | "30d" | "all";

export const PERIODS: { key: PeriodKey; label: string; hours: number | null }[] = [
  { key: "24h", label: "Last 24 hours", hours: 24 },
  { key: "7d", label: "Last 7 days", hours: 24 * 7 },
  { key: "30d", label: "Last 30 days", hours: 24 * 30 },
  { key: "all", label: "All time", hours: null },
];

/** The `since` bound for a period, or undefined for all time. */
export function sinceFor(period: PeriodKey, now = Date.now()): string | undefined {
  const hours = PERIODS.find((p) => p.key === period)?.hours ?? null;
  return hours === null ? undefined : new Date(now - hours * 3_600_000).toISOString();
}

/**
 * Below this many cases a mean or median says little. It is a display
 * convention, not a statistical test: the screen labels the figure as resting on
 * few cases and lets the reader decide.
 */
export const SMALL_SAMPLE = 5;

export function isSmallSample(sampleSize: number): boolean {
  return sampleSize > 0 && sampleSize < SMALL_SAMPLE;
}

/** 0.4 -> "under a minute"; 75 -> "1 h 15 min"; null -> "—". */
export function formatMinutes(minutes: number | null): string {
  if (minutes === null || Number.isNaN(minutes)) return "—";
  if (minutes < 1) return "under a minute";
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** Bar length as a share of the largest value, 0–1; safe for an all-zero set. */
export function barShare(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 0;
  return Math.min(1, value / max);
}

/** The coarse area a hotspot cell covers, in kilometres across (north–south). */
export function cellSizeKm(cellSizeDegrees: number): number {
  return Math.round(cellSizeDegrees * 111 * 10) / 10;
}
