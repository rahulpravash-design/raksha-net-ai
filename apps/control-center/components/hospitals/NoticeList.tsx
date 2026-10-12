"use client";

import { useState } from "react";

import {
  ApiError,
  NEXT_NOTICE_STATUSES,
  categoryLabel,
  formatRelative,
  hospitalNoticeStatusLabel,
  type HospitalNotice,
  type HospitalNoticeStatus,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

/**
 * Who may do what with a notice.
 *
 * The receiving hospital acknowledges, confirms arrival or diverts — it is the
 * only party that knows. The dispatch side may only withdraw a notice. (The
 * backend would let a dispatcher mark a notice "acknowledged" on a hospital's
 * behalf; offering that would put words in the hospital's mouth, so the screen
 * does not.)
 */
function actionsFor(
  notice: HospitalNotice,
  viewer: "hospital" | "dispatch",
): HospitalNoticeStatus[] {
  const next = NEXT_NOTICE_STATUSES[notice.status];
  return viewer === "hospital"
    ? next.filter((status) => status !== "CANCELLED")
    : next.filter((status) => status === "CANCELLED");
}

const ACTION_LABEL: Record<HospitalNoticeStatus, string> = {
  NOTIFIED: "Notified",
  ACKNOWLEDGED: "Acknowledge",
  ARRIVED: "Patient arrived",
  DIVERTED: "Divert…",
  CANCELLED: "Withdraw notice…",
};

function NoticeRow({
  notice,
  viewer,
  onChanged,
}: {
  notice: HospitalNotice;
  viewer: "hospital" | "dispatch";
  onChanged: () => void;
}) {
  const api = getApiClient();
  const [pending, setPending] = useState<HospitalNoticeStatus | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actions = actionsFor(notice, viewer);
  const needsNote = pending === "DIVERTED";

  async function apply(status: HospitalNoticeStatus) {
    setBusy(true);
    setError(null);
    try {
      await api.respondToHospitalNotice(notice.id, status, note.trim() || undefined);
      setPending(null);
      setNote("");
      onChanged();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The notice could not be updated.");
    } finally {
      setBusy(false);
    }
  }

  function choose(status: HospitalNoticeStatus) {
    // Diverting and withdrawing take a second step; the others are one click.
    if (status === "DIVERTED" || status === "CANCELLED") setPending(status);
    else void apply(status);
  }

  return (
    <li className="space-y-2 rounded-lg border border-[var(--border)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            {notice.patient_count} patient{notice.patient_count === 1 ? "" : "s"} ·{" "}
            {categoryLabel(notice.category)}
            {notice.severity ? ` · ${notice.severity.toLowerCase()}` : ""}
          </p>
          <p className="muted text-xs">
            Sent {formatRelative(notice.created_at)} by {notice.created_by.full_name}
            {notice.eta_minutes !== null ? ` · ETA about ${notice.eta_minutes} min` : ""}
          </p>
        </div>
        <span className="rounded-full border border-[var(--border)] px-2.5 py-0.5 text-xs font-semibold">
          {hospitalNoticeStatusLabel(notice.status)}
        </span>
      </div>
      {notice.clinical_notes && <p className="text-sm">Clinical notes: {notice.clinical_notes}</p>}
      {notice.response_note && <p className="text-sm">Hospital response: {notice.response_note}</p>}
      <ErrorBanner message={error} />

      {actions.length > 0 && !pending && (
        <div className="flex flex-wrap gap-2">
          {actions.map((status) => (
            <Button
              key={status}
              variant={status === "DIVERTED" || status === "CANCELLED" ? "danger" : "secondary"}
              disabled={busy}
              onClick={() => choose(status)}
            >
              {ACTION_LABEL[status]}
            </Button>
          ))}
        </div>
      )}

      {pending && (
        <div role="group" aria-label={`Confirm ${pending.toLowerCase()}`} className="space-y-2">
          <Field
            label={needsNote ? "Reason for diverting" : "Note"}
            hint={needsNote ? "Required — the control centre needs to know why." : "Optional."}
          >
            <TextInput value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button
              variant="danger"
              loading={busy}
              disabled={needsNote && note.trim() === ""}
              onClick={() => void apply(pending)}
            >
              {pending === "DIVERTED" ? "Confirm divert" : "Confirm withdraw"}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => setPending(null)}>
              Back
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

export function NoticeList({
  notices,
  viewer,
  onChanged,
  emptyText = "No inbound patients.",
}: {
  notices: HospitalNotice[];
  viewer: "hospital" | "dispatch";
  onChanged: () => void;
  emptyText?: string;
}) {
  if (notices.length === 0) return <p className="muted text-sm">{emptyText}</p>;
  return (
    <ul className="space-y-2" aria-label="Inbound notices">
      {notices.map((notice) => (
        <NoticeRow key={notice.id} notice={notice} viewer={viewer} onChanged={onChanged} />
      ))}
    </ul>
  );
}
