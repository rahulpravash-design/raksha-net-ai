"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, type HospitalNotice, type Incident } from "@raksha/api-client";

import { Button, ErrorBanner } from "@/components/ui";
import { getApiClient } from "@/lib/api";

import { NoticeList } from "./NoticeList";
import { NotifyHospital } from "./NotifyHospital";

/** Hospitals told about this incident, and (for dispatchers) a way to tell another. */
export function HospitalNoticePanel({
  incident,
  incidentOpen,
  canDispatch,
}: {
  incident: Pick<Incident, "id" | "latitude" | "longitude" | "people_affected" | "severity">;
  incidentOpen: boolean;
  canDispatch: boolean;
}) {
  const api = getApiClient();
  const [notices, setNotices] = useState<HospitalNotice[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notifying, setNotifying] = useState(false);

  const load = useCallback(async () => {
    try {
      const [rows, hospitals] = await Promise.all([
        api.incidentHospitalNotices(incident.id),
        api.hospitals({ page_size: 100, active_only: false }),
      ]);
      setNotices(rows);
      setNames(Object.fromEntries(hospitals.items.map((h) => [h.id, h.name])));
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Hospital notices could not be loaded.");
    }
  }, [api, incident.id]);

  useEffect(() => {
    // Session token is in browser storage; every setState follows an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  return (
    <section className="panel-3d space-y-3 rounded-xl p-4">
      <h2 className="font-semibold">Hospitals</h2>
      <ErrorBanner message={error} />

      {notices !== null && (
        <>
          {notices.length > 0 && (
            <ul className="muted text-xs" aria-label="Hospitals notified">
              {notices.map((notice) => (
                <li key={notice.id}>{names[notice.hospital_id] ?? "A hospital"} was notified.</li>
              ))}
            </ul>
          )}
          <NoticeList
            notices={notices}
            viewer="dispatch"
            onChanged={() => void load()}
            emptyText="No hospital has been notified for this incident."
          />
        </>
      )}

      {canDispatch && incidentOpen && !notifying && (
        <Button variant="secondary" onClick={() => setNotifying(true)}>
          Notify a hospital…
        </Button>
      )}
      {canDispatch && !incidentOpen && (
        <p className="muted text-xs">This incident is closed, so no further notices can be sent.</p>
      )}
      {!canDispatch && (
        <p className="muted text-xs">Only dispatchers and administrators can notify hospitals.</p>
      )}

      {notifying && (
        <NotifyHospital
          incident={incident}
          onCancel={() => setNotifying(false)}
          onSent={() => {
            setNotifying(false);
            void load();
          }}
        />
      )}
    </section>
  );
}
