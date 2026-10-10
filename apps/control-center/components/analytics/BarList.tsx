import { barShare } from "@/lib/analytics";

export interface BarRow {
  key: string;
  label: string;
  value: number;
  /** The figure printed on the row — the bar alone is never the only carrier. */
  valueLabel: string;
  detail?: string;
}

/**
 * Horizontal bars for one measure in one hue. Rows are labelled and valued in
 * text, so the list reads as a table without the bars; bars start at a common
 * baseline and are scaled to the largest row (never to the page).
 */
export function BarList({ rows, label }: { rows: BarRow[]; label: string }) {
  const max = Math.max(0, ...rows.map((row) => row.value));
  return (
    <ul aria-label={label} className="space-y-2.5">
      {rows.map((row) => (
        <li key={row.key}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span>{row.label}</span>
            <span className="tabular-nums font-semibold">{row.valueLabel}</span>
          </div>
          <div aria-hidden="true" className="mt-1 h-2 rounded-r bg-white/5">
            <div
              className="h-full rounded-r bg-[var(--accent)]"
              style={{ width: `${Math.round(barShare(row.value, max) * 100)}%` }}
            />
          </div>
          {row.detail && <p className="muted mt-0.5 text-xs">{row.detail}</p>}
        </li>
      ))}
    </ul>
  );
}
