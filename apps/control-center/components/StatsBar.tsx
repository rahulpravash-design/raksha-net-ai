"use client";

import { BAND_STYLES, type IncidentStats, type PriorityBand } from "@raksha/api-client";

const BANDS: PriorityBand[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export function StatsBar({ stats }: { stats: IncidentStats | null }) {
  const tiles = [
    ...BANDS.map((band) => ({
      key: band,
      label: BAND_STYLES[band].label,
      value: stats?.by_band[band] ?? 0,
      accent: BAND_STYLES[band].accent,
    })),
    {
      key: "open",
      label: "Open",
      value: stats?.total_open ?? 0,
      accent: "border-l-slate-400",
    },
    {
      key: "unassigned",
      label: "Unassigned",
      value: stats?.unassigned_open ?? 0,
      accent: "border-l-slate-400",
    },
  ];

  return (
    <dl className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      {tiles.map((tile) => (
        <div
          key={tile.key}
          className={`surface rounded-xl border-l-4 px-4 py-3 ${tile.accent}`}
        >
          <dt className="muted text-xs font-medium uppercase tracking-wide">
            {tile.label}
          </dt>
          <dd className="mt-1 text-2xl font-bold tabular-nums">{tile.value}</dd>
        </div>
      ))}
    </dl>
  );
}
