"use client";

import { motion } from "motion/react";

import { formatDateTime, statusLabel, type StatusHistoryEntry } from "@raksha/api-client";

/** The append-only status history. The newest entry is marked as current. */
export function StatusTimeline({ entries }: { entries: StatusHistoryEntry[] }) {
  if (entries.length === 0) {
    return <p className="muted text-sm">No recorded activity.</p>;
  }
  return (
    <ol className="relative space-y-4 border-l border-[var(--border)] pl-5">
      {entries.map((entry, index) => {
        const current = index === entries.length - 1;
        return (
          <motion.li
            key={entry.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: Math.min(index, 8) * 0.04 }}
            className="relative text-sm"
          >
            <span
              aria-hidden="true"
              className={`absolute -left-[1.6rem] top-1.5 h-2.5 w-2.5 rounded-full ${
                current ? "bg-[var(--accent)] ring-4 ring-[var(--accent)]/20" : "bg-[var(--muted)]"
              }`}
            />
            <p className="font-medium">
              {entry.from_status
                ? `${statusLabel(entry.from_status)} → ${statusLabel(entry.to_status)}`
                : statusLabel(entry.to_status)}
              {current && <span className="muted ml-2 text-xs font-normal">current</span>}
            </p>
            <p className="muted text-xs">
              {formatDateTime(entry.created_at)}
              {entry.changed_by ? ` · ${entry.changed_by.full_name}` : ""}
            </p>
            {entry.note && <p className="mt-1">{entry.note}</p>}
          </motion.li>
        );
      })}
    </ol>
  );
}
