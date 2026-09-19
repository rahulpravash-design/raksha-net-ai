"use client";

import Link from "next/link";

import {
  categoryLabel,
  dispatchStatusLabel,
  formatRelative,
  type ResponderAssignment,
} from "@raksha/api-client";

import { PriorityBadge } from "./ui";

/**
 * One assignment, as a crew scans it: what, where, how urgent, how far.
 *
 * The life-safety flags are rendered as words rather than icons — a crew
 * glancing at this in a moving vehicle should not have to decode a symbol.
 */
export function AssignmentCard({ assignment }: { assignment: ResponderAssignment }) {
  const { incident } = assignment;

  return (
    <li>
      <Link
        href={`/assignments/${assignment.id}`}
        className="surface block rounded-xl p-4 transition hover:border-brand-500"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-semibold">{categoryLabel(incident.category)}</span>
          <PriorityBadge band={incident.priority_band} />
        </div>

        <p className="muted mt-1 text-sm">
          {incident.reference_code} · {dispatchStatusLabel(assignment.status)} ·{" "}
          {formatRelative(assignment.created_at)}
        </p>

        {incident.address_text && (
          <p className="mt-1 truncate text-sm">{incident.address_text}</p>
        )}

        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          {incident.people_trapped && (
            <span className="rounded-full bg-red-100 px-2 py-0.5 font-semibold text-red-900 dark:bg-red-950 dark:text-red-200">
              People trapped
            </span>
          )}
          {incident.medical_required && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              Medical
            </span>
          )}
          {incident.immediate_danger && (
            <span className="rounded-full bg-orange-100 px-2 py-0.5 font-semibold text-orange-900 dark:bg-orange-950 dark:text-orange-200">
              Immediate danger
            </span>
          )}
          {assignment.estimated_minutes !== null && (
            <span className="muted rounded-full px-2 py-0.5">
              ~{assignment.estimated_minutes} min ({assignment.distance_km?.toFixed(1)} km
              direct)
            </span>
          )}
        </div>
      </Link>
    </li>
  );
}
