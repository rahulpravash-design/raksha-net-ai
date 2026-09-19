"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  NEXT_DISPATCH_STATUSES,
  categoryLabel,
  dispatchStatusLabel,
  formatCoordinates,
  formatDateTime,
  type DispatchStatus,
  type ResponderAssignment,
} from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import {
  Button,
  ErrorBanner,
  Field,
  PriorityBadge,
  Spinner,
  TextInput,
} from "@/components/ui";
import { getApiClient } from "@/lib/api";

export default function AssignmentPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [assignment, setAssignment] = useState<ResponderAssignment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      setAssignment(await api.dispatch(params.id));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "This assignment could not be loaded.",
      );
    }
  }, [api, params.id]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // Token-gated data: it cannot be fetched server-side, and every setState
    // here happens after an awaited response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [authLoading, user, router, load]);

  async function report(status: DispatchStatus) {
    setBusy(true);
    setError(null);
    try {
      await api.setDispatchStatus(params.id, status, {
        ...(status === "CANCELLED" ? { reason: reason.trim() } : {}),
      });
      await load();
      setReason("");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "That update could not be recorded.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (authLoading || !assignment) {
    return error ? <ErrorBanner message={error} /> : <Spinner label="Loading" />;
  }

  const { incident } = assignment;
  const next = NEXT_DISPATCH_STATUSES[assignment.status];
  const mapsUrl = `https://www.openstreetmap.org/?mlat=${incident.latitude}&mlon=${incident.longitude}#map=17/${incident.latitude}/${incident.longitude}`;

  return (
    <div className="space-y-4">
      <Link href="/assignments" className="muted text-sm hover:underline">
        ← All assignments
      </Link>

      <ErrorBanner message={error} />

      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{categoryLabel(incident.category)}</h1>
        <PriorityBadge band={incident.priority_band} />
        <span className="muted font-mono text-sm">{incident.reference_code}</span>
      </header>

      <section className="surface rounded-xl p-4">
        <h2 className="font-semibold">The scene</h2>
        <blockquote className="mt-2 border-l-2 border-[var(--border)] pl-3 text-sm whitespace-pre-wrap">
          {incident.description}
        </blockquote>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
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
        </dl>
      </section>

      <section className="surface rounded-xl p-4">
        <h2 className="font-semibold">Location</h2>
        <p className="mt-2 font-mono text-sm">
          {formatCoordinates(incident.latitude, incident.longitude)}
        </p>
        {incident.address_text && <p className="mt-1 text-sm">{incident.address_text}</p>}
        {incident.landmark && (
          <p className="mt-1 text-sm">Landmark: {incident.landmark}</p>
        )}
        <a
          href={mapsUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block font-semibold text-brand-600 hover:underline"
        >
          Open in maps
        </a>
        {incident.contact_phone && (
          <a
            href={`tel:${incident.contact_phone}`}
            className="mt-3 ml-4 inline-block font-semibold text-brand-600 hover:underline"
          >
            Call the scene
          </a>
        )}
        {assignment.estimated_minutes !== null && (
          <p className="muted mt-2 text-xs">
            About {assignment.estimated_minutes} min at{" "}
            {assignment.distance_km?.toFixed(1)} km direct. This is a straight-line
            estimate, not a route.
          </p>
        )}
      </section>

      <section className="surface space-y-3 rounded-xl p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-semibold">Report progress</h2>
          <span className="muted text-sm">{dispatchStatusLabel(assignment.status)}</span>
        </div>

        {next.length === 0 ? (
          <p className="muted text-sm">
            This assignment is closed. {assignment.cancel_reason ?? ""}
          </p>
        ) : (
          <>
            {next.includes("CANCELLED") && (
              <Field label="Reason" hint="Required only when standing down.">
                <TextInput
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="e.g. Stood down by the control centre"
                />
              </Field>
            )}
            <div className="flex flex-wrap gap-2">
              {next.map((status) => (
                <Button
                  key={status}
                  variant={status === "CANCELLED" ? "danger" : "primary"}
                  disabled={
                    busy || (status === "CANCELLED" && reason.trim() === "")
                  }
                  onClick={() => void report(status)}
                >
                  {dispatchStatusLabel(status)}
                </Button>
              ))}
            </div>
          </>
        )}

        <p className="muted text-xs">
          Sent by {assignment.approved_by.full_name} ·{" "}
          {formatDateTime(assignment.created_at)}
        </p>
      </section>
    </div>
  );
}
