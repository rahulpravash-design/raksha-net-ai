"use client";

import Link from "next/link";

import { categoryLabel, statusLabel } from "@raksha/api-client";

import { describeAge, useAgeSeconds } from "@/components/command-center/CommandStrip";
import { priorityTheme } from "@/lib/theme";

import { LIVE_MARKER_LIMIT, type LiveIncidents } from "./useLiveIncidents";

/** How many incidents get a chip; the rest are on the globe and the dashboard. */
const CHIP_LIMIT = 8;

/**
 * The signed-in operator's view of the globe: the platform's real open
 * incidents. It shows only what identifies one on the globe — reference,
 * category, priority and status. The report text, the reporter and the exact
 * address stay on the incident page, behind the same checks as everywhere else.
 */
export function LiveIncidentPanel({
  live,
  selectedId,
  onSelect,
}: {
  live: LiveIncidents;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const age = useAgeSeconds(live.lastUpdated);
  const selected = live.incidents.find((incident) => incident.id === selectedId) ?? null;
  const drawn = live.incidents.length;
  const open = live.totalOpen ?? drawn;

  return (
    <section aria-label="Live incidents" className="pointer-events-auto max-w-xl pb-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">
        Live incidents — from the platform
      </p>

      <p role="status" className="mt-1 text-sm">
        {live.state === "loading" || live.state === "idle" ? (
          "Loading open incidents…"
        ) : live.state === "unavailable" ? (
          "The live feed could not be reached. No incident data is shown."
        ) : (
          <>
            <strong>{open}</strong> open incident{open === 1 ? "" : "s"}
            {open > drawn ? ` — the ${drawn} highest-priority are on the globe` : ""}
            <span className="muted">
              {age === null ? "" : ` · updated ${describeAge(age)}`}
              {!live.connected ? " · connection lost, showing the last data received" : ""}
            </span>
          </>
        )}
      </p>

      {live.state === "ready" && drawn === 0 && (
        <p className="muted mt-1 text-xs">No open incidents right now.</p>
      )}

      {drawn > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2">
          {live.incidents.slice(0, CHIP_LIMIT).map((incident) => {
            const theme = priorityTheme(incident.priority_band);
            const active = incident.id === selectedId;
            return (
              <li key={incident.id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => onSelect(active ? null : incident.id)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                    active
                      ? "border-[var(--accent)] bg-[var(--accent)]/15"
                      : "border-[var(--border)] hover:border-[var(--accent)]/50"
                  }`}
                >
                  <span aria-hidden="true" style={{ color: theme.hex }}>
                    {theme.glyph}
                  </span>{" "}
                  {incident.reference_code} · {categoryLabel(incident.category)} · {theme.label}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {drawn > CHIP_LIMIT && (
        <p className="muted mt-1 text-xs">
          …and {drawn - CHIP_LIMIT} more on the globe. The dashboard lists them all
          {open > LIVE_MARKER_LIMIT ? ` (${open} open)` : ""}.
        </p>
      )}

      <p aria-live="polite" className="mt-2 min-h-5 text-sm">
        {selected ? (
          <>
            {selected.reference_code}: {categoryLabel(selected.category)},{" "}
            {priorityTheme(selected.priority_band).label.toLowerCase()} priority,{" "}
            {statusLabel(selected.status).toLowerCase()}.{" "}
            <Link
              href={`/incidents/${selected.id}`}
              className="font-semibold text-[var(--accent)] underline-offset-4 hover:underline"
            >
              Open this incident
            </Link>
          </>
        ) : (
          ""
        )}
      </p>
    </section>
  );
}
