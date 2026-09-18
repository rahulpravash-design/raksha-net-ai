"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  categoryLabel,
  citizenStatusMessage,
  formatDateTime,
  statusLabel,
  type Incident,
  type StatusHistoryEntry,
} from "@raksha/api-client";

import {
  Button,
  ErrorBanner,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { getApiClient } from "@/lib/api";

/** Statuses at which the reporter may still withdraw their own report. */
const CANCELLABLE = ["REPORTED", "RECEIVED", "UNDER_REVIEW", "PRIORITIZED"];

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const api = getApiClient();

  const [incident, setIncident] = useState<Incident | null>(null);
  const [history, setHistory] = useState<StatusHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

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
        caught instanceof ApiError && caught.status === 404
          ? "This report could not be found."
          : "The report could not be loaded.",
      );
    }
  }, [api, params.id]);

  useEffect(() => {
    // The session token lives in browser storage, so this data cannot be
    // fetched in a server component — it has to be loaded on mount. The rule
    // guards against cascading synchronous renders; every setState here
    // happens after an awaited response, which is not that case.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function cancelReport() {
    if (!incident) return;
    setCancelling(true);
    try {
      await api.changeStatus(incident.id, "CANCELLED", "Withdrawn by the reporter.");
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The report could not be cancelled.",
      );
    } finally {
      setCancelling(false);
    }
  }

  if (!incident) {
    return error ? <ErrorBanner message={error} /> : <Spinner label="Loading report" />;
  }

  return (
    <div className="space-y-6">
      <Link href="/reports" className="muted text-sm hover:underline">
        ← All my reports
      </Link>

      <ErrorBanner message={error} />

      {searchParams.get("media_failed") === "1" && (
        <div
          role="alert"
          className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
        >
          Your report was filed, but at least one photograph did not upload. The
          control centre has everything else.
        </div>
      )}

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">
            {categoryLabel(incident.category)}
          </h1>
          <StatusBadge status={incident.status} />
        </div>
        <p className="muted text-sm">
          Reference <span className="font-mono">{incident.reference_code}</span> ·
          filed {formatDateTime(incident.created_at)}
        </p>
      </header>

      <section className="surface rounded-xl p-4">
        <h2 className="text-sm font-semibold">Current status</h2>
        <p className="mt-1">{citizenStatusMessage(incident.status)}</p>
      </section>

      <section className="surface rounded-xl p-4">
        <h2 className="text-sm font-semibold">What you reported</h2>
        <p className="mt-2 whitespace-pre-wrap text-sm">{incident.description}</p>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          {incident.people_affected !== null && (
            <div>
              <dt className="muted">People affected</dt>
              <dd className="font-medium">{incident.people_affected}</dd>
            </div>
          )}
          {incident.landmark && (
            <div>
              <dt className="muted">Landmark</dt>
              <dd className="font-medium">{incident.landmark}</dd>
            </div>
          )}
          {incident.media.length > 0 && (
            <div>
              <dt className="muted">Photographs</dt>
              <dd className="font-medium">{incident.media.length} attached</dd>
            </div>
          )}
        </dl>
      </section>

      <section className="surface rounded-xl p-4">
        <h2 className="text-sm font-semibold">Progress</h2>
        <ol className="mt-3 space-y-3">
          {history.map((entry) => (
            <li key={entry.id} className="flex gap-3 text-sm">
              <span
                aria-hidden="true"
                className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500"
              />
              <div>
                <p className="font-medium">{statusLabel(entry.to_status)}</p>
                <p className="muted text-xs">{formatDateTime(entry.created_at)}</p>
                {entry.note && <p className="mt-1 text-sm">{entry.note}</p>}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {CANCELLABLE.includes(incident.status) && (
        <section className="space-y-2">
          <Button
            variant="secondary"
            loading={cancelling}
            onClick={() => void cancelReport()}
          >
            Withdraw this report
          </Button>
          <p className="muted text-xs">
            Only withdraw a report if it was filed in error or the situation is
            fully resolved. Once a crew has been assigned, contact the control
            centre instead.
          </p>
        </section>
      )}
    </div>
  );
}
