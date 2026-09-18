"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  canDispatch,
  categoryLabel,
  formatCoordinates,
  formatDateTime,
  statusLabel,
  type Incident,
  type IncidentStatus,
  type PriorityBand,
  type StatusHistoryEntry,
} from "@raksha/api-client";

import { AIAnalysisPanel } from "@/components/AIAnalysisPanel";
import { useAuth } from "@/components/AuthProvider";
import { MediaGallery } from "@/components/MediaGallery";
import { PriorityExplanation } from "@/components/PriorityExplanation";
import {
  Button,
  ErrorBanner,
  Field,
  Spinner,
  StatusBadge,
  TextInput,
} from "@/components/ui";
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

export default function IncidentConsolePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [incident, setIncident] = useState<Incident | null>(null);
  const [history, setHistory] = useState<StatusHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [note, setNote] = useState("");
  const [overrideBand, setOverrideBand] = useState<PriorityBand | "">("");
  const [overrideReason, setOverrideReason] = useState("");

  const load = useCallback(async () => {
    try {
      const [detail, entries] = await Promise.all([
        api.incident(params.id),
        api.incidentHistory(params.id),
      ]);
      setIncident(detail);
      setHistory(entries);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The incident could not be loaded.",
      );
    }
  }, [api, params.id]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // The session token lives in browser storage, so this data cannot be
    // fetched in a server component — it has to be loaded on mount. The rule
    // guards against cascading synchronous renders; every setState here
    // happens after an awaited response, which is not that case.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [authLoading, user, router, load]);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
      setNote("");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "That action could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (authLoading || !incident) {
    return error ? <ErrorBanner message={error} /> : <Spinner label="Loading incident" />;
  }

  const mayDispatch = user ? canDispatch(user.role) : false;
  const nextStatuses = NEXT_STATUSES[incident.status];

  return (
    <div className="space-y-4">
      <Link href="/dashboard" className="muted text-sm hover:underline">
        ← Back to the queue
      </Link>

      <ErrorBanner message={error} />

      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{categoryLabel(incident.category)}</h1>
        <StatusBadge status={incident.status} />
        <span className="muted font-mono text-sm">{incident.reference_code}</span>
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <section className="surface rounded-xl p-4">
            <h2 className="font-semibold">Reported situation</h2>
            <blockquote className="mt-2 border-l-2 border-[var(--border)] pl-3 text-sm whitespace-pre-wrap">
              {incident.description}
            </blockquote>
            <p className="muted mt-2 text-xs">
              The reporter&apos;s own words, unedited.
            </p>

            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="muted">People affected</dt>
                <dd className="font-medium">{incident.people_affected ?? "Unknown"}</dd>
              </div>
              <div>
                <dt className="muted">Trapped</dt>
                <dd className="font-medium">
                  {incident.people_trapped ? "Yes" : "Not reported"}
                </dd>
              </div>
              <div>
                <dt className="muted">Medical support</dt>
                <dd className="font-medium">
                  {incident.medical_required ? "Required" : "Not reported"}
                </dd>
              </div>
              <div>
                <dt className="muted">Immediate danger</dt>
                <dd className="font-medium">
                  {incident.immediate_danger ? "Yes" : "Not reported"}
                </dd>
              </div>
              <div>
                <dt className="muted">Reported</dt>
                <dd className="font-medium">{formatDateTime(incident.created_at)}</dd>
              </div>
              <div>
                <dt className="muted">Contact</dt>
                <dd className="font-medium">{incident.contact_phone ?? "—"}</dd>
              </div>
            </dl>
          </section>

          <AIAnalysisPanel
            incidentId={incident.id}
            canReview={mayDispatch}
            onApplied={() => void load()}
          />

          <section className="surface rounded-xl p-4">
            <h2 className="font-semibold">Location</h2>
            <p className="mt-2 font-mono text-sm">
              {formatCoordinates(incident.latitude, incident.longitude)}
            </p>
            {incident.location_accuracy_m !== null && (
              <p
                className={
                  incident.location_accuracy_m > 100
                    ? "mt-1 text-sm text-amber-700 dark:text-amber-300"
                    : "muted mt-1 text-sm"
                }
              >
                Device accuracy about {incident.location_accuracy_m} m
                {incident.location_accuracy_m > 100 ? " — treat as approximate." : ""}
              </p>
            )}
            {incident.address_text && <p className="mt-1 text-sm">{incident.address_text}</p>}
            {incident.landmark && (
              <p className="mt-1 text-sm">Landmark: {incident.landmark}</p>
            )}
          </section>

          <section className="surface rounded-xl p-4">
            <h2 className="font-semibold">Photographs</h2>
            <div className="mt-3">
              <MediaGallery media={incident.media} />
            </div>
          </section>

          <section className="surface rounded-xl p-4">
            <h2 className="font-semibold">Audit trail</h2>
            <ol className="mt-3 space-y-3">
              {history.map((entry) => (
                <li key={entry.id} className="flex gap-3 text-sm">
                  <span
                    aria-hidden="true"
                    className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500"
                  />
                  <div>
                    <p className="font-medium">
                      {entry.from_status
                        ? `${statusLabel(entry.from_status)} → ${statusLabel(entry.to_status)}`
                        : statusLabel(entry.to_status)}
                    </p>
                    <p className="muted text-xs">
                      {formatDateTime(entry.created_at)}
                      {entry.changed_by ? ` · ${entry.changed_by.full_name}` : ""}
                    </p>
                    {entry.note && <p className="mt-1">{entry.note}</p>}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="space-y-4">
          <PriorityExplanation incident={incident} />

          {mayDispatch ? (
            <>
              <section className="surface space-y-3 rounded-xl p-4">
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
                          void act(() =>
                            api.changeStatus(
                              incident.id,
                              status,
                              note.trim() || undefined,
                            ),
                          )
                        }
                      >
                        {statusLabel(status)}
                      </Button>
                    ))}
                  </div>
                )}
                {nextStatuses.includes("DUPLICATE") && (
                  <p className="muted text-xs">
                    Marking a duplicate needs the other incident&apos;s id, so it
                    is done from the incident it duplicates.
                  </p>
                )}
              </section>

              <section className="surface space-y-3 rounded-xl p-4">
                <h2 className="font-semibold">Override priority</h2>
                <p className="muted text-xs">
                  Use this when you know something the engine does not. The reason
                  is mandatory and is attributed to you.
                </p>

                <Field label="Band">
                  <select
                    aria-label="Override band"
                    className="surface w-full rounded-lg px-3 py-2.5 text-sm"
                    value={overrideBand}
                    onChange={(event) =>
                      setOverrideBand(event.target.value as PriorityBand | "")
                    }
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
          ) : (
            <section className="surface rounded-xl p-4">
              <p className="muted text-sm">
                Your role can view this incident but not change it. Dispatch
                actions are limited to dispatchers and administrators.
              </p>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
