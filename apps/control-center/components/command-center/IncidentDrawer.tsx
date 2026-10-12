"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { categoryLabel } from "@raksha/api-client";

import { LocationBody, SituationBody } from "@/components/incident/SituationPanel";
import { StatusTimeline } from "@/components/incident/StatusTimeline";
import { PriorityBadge, StatusBadge } from "@/components/ui";

import type { SelectedDetail } from "./SelectedIncident";

/**
 * A slide-over with the full incident, so a dispatcher can read it without
 * losing the map. It is a modal dialog: focus moves in, Escape or the backdrop
 * closes it, and focus returns to what opened it. It shows only what the API
 * returned for this incident.
 */
export function IncidentDrawer({
  open,
  detail,
  onClose,
}: {
  open: boolean;
  detail: SelectedDetail;
  onClose: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open, onClose]);

  const { incident, history, error } = detail;

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[1000]">
          <motion.button
            type="button"
            aria-label="Close incident details"
            tabIndex={-1}
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 cursor-default bg-black/60"
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label="Incident details"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.25 }}
            className="panel-3d absolute right-0 top-0 flex h-full w-full max-w-xl flex-col overflow-y-auto rounded-l-xl p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold">
                  {incident ? categoryLabel(incident.category) : "Incident"}
                </h2>
                {incident && (
                  <p className="muted font-mono text-xs">{incident.reference_code}</p>
                )}
              </div>
              <button
                ref={closeButton}
                type="button"
                onClick={onClose}
                className="surface rounded-lg px-3 py-1.5 text-sm font-semibold"
              >
                Close
              </button>
            </div>

            {error && (
              <p role="alert" className="mt-3 text-sm text-red-300">
                {error}
              </p>
            )}

            {incident && (
              <div className="mt-4 space-y-5">
                <div className="flex flex-wrap gap-2">
                  <StatusBadge status={incident.status} />
                  <PriorityBadge band={incident.priority_band} />
                </div>
                <section aria-label="Reported situation">
                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--accent)]">
                    Reported situation
                  </h3>
                  <SituationBody incident={incident} />
                </section>
                <section aria-label="Location">
                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--accent)]">
                    Location
                  </h3>
                  <LocationBody incident={incident} />
                </section>
                <section aria-label="Status history">
                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--accent)]">
                    Status history
                  </h3>
                  <StatusTimeline entries={history ?? []} />
                </section>
                <Link
                  href={`/incidents/${incident.id}`}
                  className="block rounded-lg bg-brand-600 px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-brand-700"
                >
                  Open incident console
                </Link>
              </div>
            )}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
