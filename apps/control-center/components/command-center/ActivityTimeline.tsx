"use client";

import { AnimatePresence, motion } from "motion/react";

import { formatDateTime, statusLabel, type StatusHistoryEntry } from "@raksha/api-client";

/** The selected incident's real status history, oldest to newest. */
export function ActivityTimeline({
  entries,
  loading,
  error,
}: {
  entries: StatusHistoryEntry[] | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <section aria-label="Incident activity" className="panel-3d rounded-xl p-3">
      <h2 className="text-sm font-semibold">Activity timeline</h2>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {error}
        </p>
      )}
      {!error && entries === null && (
        <p className="muted mt-2 text-sm">
          {loading ? "Loading activity…" : "Select an incident to see its activity."}
        </p>
      )}
      {entries !== null && entries.length === 0 && (
        <p className="muted mt-2 text-sm">No recorded activity.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <ol className="mt-2 flex gap-4 overflow-x-auto pb-1">
          <AnimatePresence initial={false}>
            {entries.map((entry) => (
              <motion.li
                key={entry.id}
                layout
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                className="min-w-48 shrink-0 border-l-2 border-[var(--accent)]/60 pl-3 text-sm"
              >
                <p className="font-semibold">{statusLabel(entry.to_status)}</p>
                <p className="muted text-xs">
                  {formatDateTime(entry.created_at)}
                  {entry.changed_by ? ` · ${entry.changed_by.full_name}` : ""}
                </p>
                {entry.note && <p className="mt-0.5 text-xs">{entry.note}</p>}
              </motion.li>
            ))}
          </AnimatePresence>
        </ol>
      )}
    </section>
  );
}
