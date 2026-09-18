"use client";

import type { Incident } from "@raksha/api-client";

import { PriorityBadge } from "./ui";

/**
 * Why this incident scored what it scored.
 *
 * The engine records every contributing factor precisely so a dispatcher can
 * audit the number rather than trust it. A score with no explanation would be
 * exactly the opaque ranking this platform sets out to avoid.
 */
export function PriorityExplanation({ incident }: { incident: Incident }) {
  const factors = incident.priority_factors ?? [];

  return (
    <section className="surface rounded-xl p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">Priority</h2>
        <PriorityBadge band={incident.priority_band} />
      </div>

      {incident.priority_overridden && (
        <div className="mt-3 rounded-lg border border-purple-300 bg-purple-50 px-3 py-2 text-sm dark:border-purple-800 dark:bg-purple-950/40">
          <p className="font-semibold">Overridden by an operator</p>
          {incident.priority_override_reason && (
            <p className="mt-1">{incident.priority_override_reason}</p>
          )}
          <p className="muted mt-1 text-xs">
            The engine&apos;s own score of {incident.priority_score} is kept below
            for comparison.
          </p>
        </div>
      )}

      <p className="muted mt-3 text-sm">
        Engine score{" "}
        <span className="font-bold tabular-nums text-[var(--foreground)]">
          {incident.priority_score ?? "—"}
        </span>{" "}
        out of 100
      </p>

      {factors.length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {factors.map((factor) => (
            <li
              key={factor.key}
              className="flex items-baseline justify-between gap-3 text-sm"
            >
              <span>{factor.label}</span>
              <span className="muted shrink-0 tabular-nums">
                +{factor.points}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted mt-3 text-sm">No contributing factors recorded.</p>
      )}

      <p className="muted mt-4 text-xs">
        Computed by the deterministic priority engine from the facts on this
        incident. It is a recommendation — the dispatcher decides.
      </p>
    </section>
  );
}
