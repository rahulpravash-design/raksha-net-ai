"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  NEXT_DISPATCH_STATUSES,
  dispatchStatusLabel,
  formatDateTime,
  resourceTypeLabel,
  type Dispatch,
  type ResourceRecommendation,
  type ResourceRecommendations,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

function errorText(caught: unknown, fallback: string): string {
  return caught instanceof ApiError ? caught.message : fallback;
}

function isStandable(dispatch: Dispatch): boolean {
  return NEXT_DISPATCH_STATUSES[dispatch.status].includes("CANCELLED");
}

function RecommendationRow({
  item,
  confirming,
  disabled,
  note,
  onNote,
  onChoose,
  onCancel,
  onConfirm,
}: {
  item: ResourceRecommendation;
  confirming: boolean;
  disabled: boolean;
  note: string;
  onNote: (value: string) => void;
  onChoose: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { resource } = item;
  return (
    <li className="rounded-lg border border-[var(--border)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            <span className="muted mr-1">#{item.rank}</span>
            {resource.call_sign} · {resource.name}
          </p>
          <p className="muted text-xs">
            {resourceTypeLabel(resource.resource_type)} ·{" "}
            {resource.distance_km.toFixed(1)} km away · about{" "}
            {item.estimated_minutes} min (straight-line estimate)
          </p>
        </div>
        {!confirming && (
          <Button variant="secondary" disabled={disabled} onClick={onChoose}>
            Dispatch…
          </Button>
        )}
      </div>

      <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs">
        {item.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>

      {confirming && (
        <div
          role="group"
          aria-label={`Confirm dispatch of ${resource.call_sign}`}
          className="mt-3 space-y-2 rounded-lg bg-[var(--surface-2,transparent)] p-2"
        >
          <p className="text-sm font-medium">
            Send {resource.call_sign} to this incident? You will be recorded as
            the approving dispatcher.
          </p>
          <Field label="Note for the crew" hint="Optional.">
            <TextInput value={note} onChange={(e) => onNote(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button disabled={disabled} onClick={onConfirm}>
              Confirm dispatch
            </Button>
            <Button variant="secondary" disabled={disabled} onClick={onCancel}>
              Not now
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

function DispatchRow({
  dispatch,
  canStandDown,
  standingDown,
  reason,
  disabled,
  onReason,
  onStart,
  onAbort,
  onConfirm,
}: {
  dispatch: Dispatch;
  canStandDown: boolean;
  standingDown: boolean;
  reason: string;
  disabled: boolean;
  onReason: (value: string) => void;
  onStart: () => void;
  onAbort: () => void;
  onConfirm: () => void;
}) {
  return (
    <li className="rounded-lg border border-[var(--border)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            {dispatch.resource.call_sign} · {dispatch.resource.name}
          </p>
          <p className="muted text-xs">
            Approved by {dispatch.approved_by.full_name} ·{" "}
            {formatDateTime(dispatch.created_at)}
          </p>
        </div>
        <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs font-semibold">
          {dispatchStatusLabel(dispatch.status)}
        </span>
      </div>
      {dispatch.estimated_minutes !== null && dispatch.distance_km !== null && (
        <p className="muted mt-1 text-xs">
          {dispatch.distance_km.toFixed(1)} km · about {dispatch.estimated_minutes}{" "}
          min at dispatch (straight-line estimate)
        </p>
      )}
      {dispatch.note && <p className="mt-1 text-sm">Note: {dispatch.note}</p>}
      {dispatch.cancel_reason && (
        <p className="mt-1 text-sm">Stood down: {dispatch.cancel_reason}</p>
      )}

      {canStandDown && isStandable(dispatch) && !standingDown && (
        <div className="mt-2">
          <Button variant="danger" disabled={disabled} onClick={onStart}>
            Stand down…
          </Button>
        </div>
      )}

      {standingDown && (
        <div
          role="group"
          aria-label={`Stand down ${dispatch.resource.call_sign}`}
          className="mt-3 space-y-2"
        >
          <Field label="Reason" hint="Required. Recorded in the audit trail.">
            <TextInput value={reason} onChange={(e) => onReason(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button
              variant="danger"
              disabled={disabled || reason.trim().length === 0}
              onClick={onConfirm}
            >
              Confirm stand down
            </Button>
            <Button variant="secondary" disabled={disabled} onClick={onAbort}>
              Keep dispatched
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

/**
 * Dispatch workflow for one incident.
 *
 * CLAUDE.md section 2, rule 1: the system ranks, a human decides. Ranking is
 * shown with its reasons; nothing is sent until a dispatcher presses the
 * second, explicit "Confirm dispatch". There is no approver field — the
 * backend records whoever is signed in, so the UI cannot name someone else.
 */
export function DispatchPanel({
  incidentId,
  incidentOpen,
  canDispatch,
  onChanged,
}: {
  incidentId: string;
  incidentOpen: boolean;
  canDispatch: boolean;
  onChanged: () => void;
}) {
  const api = getApiClient();
  const [dispatches, setDispatches] = useState<Dispatch[] | null>(null);
  const [recs, setRecs] = useState<ResourceRecommendations | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [standDownId, setStandDownId] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const showRecs = canDispatch && incidentOpen;

  const load = useCallback(async () => {
    try {
      const [rows, ranked] = await Promise.all([
        api.incidentDispatches(incidentId),
        showRecs ? api.resourceRecommendations(incidentId, 5) : Promise.resolve(null),
      ]);
      setDispatches(rows);
      setRecs(ranked);
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Dispatch information could not be loaded."));
    }
  }, [api, incidentId, showRecs]);

  useEffect(() => {
    // Session token is in browser storage; every setState follows an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function dispatchResource(resourceId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.dispatchResource(incidentId, resourceId, note.trim() || undefined);
      setConfirmId(null);
      setNote("");
      await load();
      onChanged();
    } catch (caught) {
      const message = errorText(caught, "The dispatch could not be created.");
      // Someone else may have committed the unit: show the fresh ranking, then
      // restore the message (a successful reload clears the error banner).
      setConfirmId(null);
      await load();
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function standDown(dispatchId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.setDispatchStatus(dispatchId, "CANCELLED", {
        reason: reason.trim(),
      });
      setStandDownId(null);
      setReason("");
      await load();
      onChanged();
    } catch (caught) {
      setError(errorText(caught, "The unit could not be stood down."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="surface space-y-3 rounded-xl p-4">
      <h2 className="font-semibold">Dispatch</h2>
      <ErrorBanner message={error} />

      {dispatches !== null && dispatches.length === 0 && (
        <p className="muted text-sm">No unit has been dispatched yet.</p>
      )}
      {dispatches !== null && dispatches.length > 0 && (
        <ul className="space-y-2" aria-label="Dispatches">
          {dispatches.map((dispatch) => (
            <DispatchRow
              key={dispatch.id}
              dispatch={dispatch}
              canStandDown={canDispatch}
              standingDown={standDownId === dispatch.id}
              reason={reason}
              disabled={busy}
              onReason={setReason}
              onStart={() => {
                setStandDownId(dispatch.id);
                setReason("");
              }}
              onAbort={() => setStandDownId(null)}
              onConfirm={() => void standDown(dispatch.id)}
            />
          ))}
        </ul>
      )}

      {!canDispatch && (
        <p className="muted text-xs">
          Only dispatchers and administrators can dispatch or stand down units.
        </p>
      )}
      {canDispatch && !incidentOpen && (
        <p className="muted text-xs">
          This incident is closed, so no further units can be dispatched.
        </p>
      )}

      {showRecs && recs !== null && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Suggested units</h3>
          <p className="muted text-xs">
            Suggestions only, ranked within {recs.searched_radius_km} km. Dispatching
            a unit does not change the incident&apos;s status — move it yourself
            once the unit is committed.
          </p>
          {recs.note && <p className="text-xs">{recs.note}</p>}
          {recs.items.length === 0 && (
            <p className="muted text-sm">No available unit was found nearby.</p>
          )}
          <ul className="space-y-2" aria-label="Suggested units">
            {recs.items.map((item) => (
              <RecommendationRow
                key={item.resource.id}
                item={item}
                confirming={confirmId === item.resource.id}
                disabled={busy}
                note={note}
                onNote={setNote}
                onChoose={() => {
                  setConfirmId(item.resource.id);
                  setNote("");
                }}
                onCancel={() => setConfirmId(null)}
                onConfirm={() => void dispatchResource(item.resource.id)}
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
