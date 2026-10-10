"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, formatDateTime, type Hospital, type HospitalNotice } from "@raksha/api-client";

import { Button, ErrorBanner } from "@/components/ui";
import { getApiClient } from "@/lib/api";

import { CapacityForm } from "./CapacityForm";
import { CapacityMeter } from "./CapacityMeter";
import { AcceptingTag } from "./HospitalCard";
import { NoticeList } from "./NoticeList";

/**
 * One hospital. Notices are loaded only when the viewer may see them — a
 * hospital reads its own, a dispatcher reads all; for anyone else the API would
 * answer "not found", so the panel does not ask.
 */
export function HospitalDetail({
  hospital,
  canSeeNotices,
  canReportCapacity,
  noticeViewer,
  onChanged,
}: {
  hospital: Hospital;
  canSeeNotices: boolean;
  canReportCapacity: boolean;
  noticeViewer: "hospital" | "dispatch";
  onChanged: (hospital?: Hospital) => void;
}) {
  const api = getApiClient();
  const [editing, setEditing] = useState(false);
  const [notices, setNotices] = useState<HospitalNotice[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadNotices = useCallback(async () => {
    if (!canSeeNotices) return;
    try {
      setNotices(await api.hospitalNotices(hospital.id, true));
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Inbound notices could not be loaded.");
    }
  }, [api, hospital.id, canSeeNotices]);

  useEffect(() => {
    // Session token is in browser storage; every setState follows an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadNotices();
    const timer = setInterval(() => void loadNotices(), 15_000);
    return () => clearInterval(timer);
  }, [loadNotices]);

  return (
    <section aria-label="Hospital detail" className="panel-3d space-y-4 rounded-xl p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">{hospital.name}</h2>
          <p className="muted text-xs">
            {hospital.code}
            {hospital.address ? ` · ${hospital.address}` : ""}
          </p>
        </div>
        <AcceptingTag accepting={hospital.accepting_emergencies} />
      </div>

      {editing ? (
        <CapacityForm
          hospital={hospital}
          onCancel={() => setEditing(false)}
          onSaved={(updated) => {
            setEditing(false);
            onChanged(updated);
          }}
        />
      ) : (
        <div className="space-y-3">
          <CapacityMeter label="beds" available={hospital.available_beds} total={hospital.total_beds} />
          <CapacityMeter label="ICU beds" available={hospital.icu_available} total={hospital.icu_total} />
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div className="col-span-2">
              <dt className="muted">Specialties</dt>
              <dd>{hospital.specialties.length > 0 ? hospital.specialties.join(", ") : "None recorded"}</dd>
            </div>
            <div>
              <dt className="muted">Contact</dt>
              <dd>{hospital.contact_phone ?? "—"}</dd>
            </div>
            <div>
              <dt className="muted">Capacity reported</dt>
              <dd>{hospital.capacity_updated_at ? formatDateTime(hospital.capacity_updated_at) : "Never"}</dd>
            </div>
          </dl>
          {canReportCapacity && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Report capacity
            </Button>
          )}
        </div>
      )}

      {canSeeNotices ? (
        <div className="space-y-2 border-t border-[var(--border)] pt-3">
          <h3 className="text-sm font-semibold">Inbound patients</h3>
          <ErrorBanner message={error} />
          {notices === null && !error ? (
            <p className="muted text-sm">Loading…</p>
          ) : (
            <NoticeList
              notices={notices ?? []}
              viewer={noticeViewer}
              onChanged={() => void loadNotices()}
            />
          )}
          <p className="muted text-xs">
            A notice carries category, severity, patient count, ETA and the dispatcher&apos;s
            clinical notes. It never carries the reporter, their contact details or the report text.
          </p>
        </div>
      ) : (
        <p className="muted border-t border-[var(--border)] pt-3 text-xs">
          Inbound patients are visible to this hospital&apos;s own operators and to dispatchers.
        </p>
      )}
    </section>
  );
}
