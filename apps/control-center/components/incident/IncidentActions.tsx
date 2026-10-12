"use client";

import { useState } from "react";

import {
  ApiError,
  statusLabel,
  type Incident,
  type IncidentStatus,
  type PriorityBand,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

/**
 * Mirrors the backend state machine so the console offers only legal moves.
 *
 * The backend remains the authority — it validates every transition — but
 * showing a dispatcher a button that can only fail is its own kind of hazard.
 */
const NEXT_STATUSES: Record<IncidentStatus, IncidentStatus[]> = {
  REPORTED: ["RECEIVED", "UNDER_REVIEW", "DUPLICATE", "REJECTED"],
  RECEIVED: ["UNDER_REVIEW", "PRIORITIZED", "DUPLICATE", "REJECTED"],
  UNDER_REVIEW: ["PRIORITIZED", "ASSIGNED", "DUPLICATE", "REJECTED"],
  PRIORITIZED: ["ASSIGNED", "UNDER_REVIEW", "DUPLICATE", "REJECTED"],
  ASSIGNED: ["RESPONDER_EN_ROUTE", "ON_SCENE", "RESOLVED", "PRIORITIZED"],
  RESPONDER_EN_ROUTE: ["ON_SCENE", "RESOLVED", "ASSIGNED"],
  ON_SCENE: ["RESOLVED", "RESPONDER_EN_ROUTE"],
  RESOLVED: ["CLOSED", "ON_SCENE"],
  CLOSED: [],
  CANCELLED: [],
  DUPLICATE: [],
  REJECTED: [],
};

const BANDS: PriorityBand[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

/** Status moves and priority override: the dispatcher's two direct levers. */
export function IncidentActions({
  incident,
  onChanged,
}: {
  incident: Incident;
  onChanged: () => Promise<void> | void;
}) {
  const api = getApiClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [overrideBand, setOverrideBand] = useState<PriorityBand | "">("");
  const [overrideReason, setOverrideReason] = useState("");
  const nextStatuses = NEXT_STATUSES[incident.status];

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await onChanged();
      setNote("");
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "That action could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ErrorBanner message={error} />
      <section className="panel-3d space-y-3 rounded-xl p-4">
        <h2 className="font-semibold">Move this incident</h2>
        <Field label="Note" hint="Recorded in the audit trail.">
          <TextInput
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="What you did and why"
          />
        </Field>

        {nextStatuses.length === 0 ? (
          <p className="muted text-sm">
            This incident is closed. No further transitions are possible.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {nextStatuses.map((status) => (
              <Button
                key={status}
                variant={status === "REJECTED" ? "danger" : "secondary"}
                disabled={busy}
                onClick={() =>
                  void act(() => api.changeStatus(incident.id, status, note.trim() || undefined))
                }
              >
                {statusLabel(status)}
              </Button>
            ))}
          </div>
        )}
        {nextStatuses.includes("DUPLICATE") && (
          <p className="muted text-xs">
            Marking a duplicate needs the other incident&apos;s id, so it is done from the
            incident it duplicates.
          </p>
        )}
      </section>

      <section className="panel-3d space-y-3 rounded-xl p-4">
        <h2 className="font-semibold">Override priority</h2>
        <p className="muted text-xs">
          Use this when you know something the engine does not. The reason is mandatory and is
          attributed to you.
        </p>

        <Field label="Band">
          <select
            aria-label="Override band"
            className="surface w-full rounded-lg px-3 py-2.5 text-sm"
            value={overrideBand}
            onChange={(event) => setOverrideBand(event.target.value as PriorityBand | "")}
          >
            <option value="">Select a band</option>
            {BANDS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Reason" required>
          <TextInput
            value={overrideReason}
            onChange={(event) => setOverrideReason(event.target.value)}
            placeholder="e.g. Reporter confirmed by phone"
          />
        </Field>

        <div className="flex flex-wrap gap-2">
          <Button
            disabled={busy || !overrideBand || overrideReason.trim() === ""}
            onClick={() =>
              void act(async () => {
                const result = await api.overridePriority(
                  incident.id,
                  overrideBand as PriorityBand,
                  overrideReason.trim(),
                );
                setOverrideBand("");
                setOverrideReason("");
                return result;
              })
            }
          >
            Apply override
          </Button>
          <Button
            variant="secondary"
            disabled={busy || !incident.priority_overridden}
            onClick={() => void act(() => api.recalculatePriority(incident.id))}
          >
            Recalculate
          </Button>
        </div>
      </section>
    </>
  );
}
