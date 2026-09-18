"use client";

import {
  bandStyle,
  categoryLabel,
  formatRelative,
  type IncidentSummary,
} from "@raksha/api-client";

import { PriorityBadge, StatusBadge } from "./ui";

/**
 * The triage queue.
 *
 * Ordering comes from the backend (priority first, oldest first within a band).
 * The client never re-sorts: two views of "what is most urgent" would be one
 * view too many.
 */
export function IncidentQueue({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: IncidentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (incidents.length === 0) {
    return (
      <p className="muted px-4 py-10 text-center text-sm">
        No incidents match the current filters.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-[var(--border)]">
      {incidents.map((incident) => {
        const style = bandStyle(incident.priority_band);
        const isSelected = incident.id === selectedId;

        return (
          <li key={incident.id}>
            <button
              type="button"
              onClick={() => onSelect(incident.id)}
              aria-current={isSelected ? "true" : undefined}
              className={`w-full border-l-4 px-4 py-3 text-left transition ${style.accent} ${
                isSelected
                  ? "bg-brand-50 dark:bg-brand-900/30"
                  : "hover:bg-slate-50 dark:hover:bg-slate-800/60"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">
                  {categoryLabel(incident.category)}
                </span>
                <PriorityBadge band={incident.priority_band} />
              </div>

              <div className="muted mt-1 flex flex-wrap items-center gap-x-2 text-xs">
                <span className="font-mono">{incident.reference_code}</span>
                <span aria-hidden="true">·</span>
                <span>{formatRelative(incident.created_at)}</span>
                {incident.priority_score !== null && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>score {incident.priority_score}</span>
                  </>
                )}
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <StatusBadge status={incident.status} />
                {incident.people_trapped && (
                  <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-800 dark:bg-red-950 dark:text-red-200">
                    Trapped
                  </span>
                )}
                {incident.medical_required && (
                  <span className="rounded bg-sky-100 px-1.5 py-0.5 text-xs font-semibold text-sky-800 dark:bg-sky-950 dark:text-sky-200">
                    Medical
                  </span>
                )}
                {incident.priority_overridden && (
                  <span className="rounded bg-purple-100 px-1.5 py-0.5 text-xs font-semibold text-purple-800 dark:bg-purple-950 dark:text-purple-200">
                    Overridden
                  </span>
                )}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
