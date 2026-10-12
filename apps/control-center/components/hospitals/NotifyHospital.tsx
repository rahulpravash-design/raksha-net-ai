"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  type CreateHospitalNoticeInput,
  type Incident,
  type NearbyHospital,
  type SeverityLevel,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

const SEVERITIES: SeverityLevel[] = ["CRITICAL", "HIGH", "MODERATE", "LOW"];
const RADIUS_KM = 20;

/**
 * Tell a hospital a patient is coming. Three steps: pick a hospital, fill in
 * what it needs, review and send. Nothing is sent until the last button. The
 * hospital receives only category, severity, count, ETA and the clinical notes
 * written here — never the reporter, contact details, report text or location.
 */
export function NotifyHospital({
  incident,
  onSent,
  onCancel,
}: {
  incident: Pick<Incident, "id" | "latitude" | "longitude" | "people_affected" | "severity">;
  onSent: () => void;
  onCancel: () => void;
}) {
  const api = getApiClient();
  const [candidates, setCandidates] = useState<NearbyHospital[] | null>(null);
  const [chosen, setChosen] = useState<NearbyHospital | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [count, setCount] = useState(String(incident.people_affected ?? 1));
  const [severity, setSeverity] = useState<SeverityLevel | "">("");
  const [eta, setEta] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<{ count?: string; eta?: string }>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await api.hospitalsNearby({
          latitude: Number(incident.latitude),
          longitude: Number(incident.longitude),
          radius_km: RADIUS_KM,
          accepting_only: true,
          limit: 8,
        });
        if (!cancelled) setCandidates(result.items);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Hospitals could not be loaded.");
          setCandidates([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, incident.latitude, incident.longitude]);

  function review() {
    const found: { count?: string; eta?: string } = {};
    const patients = Number(count);
    if (!Number.isInteger(patients) || patients < 1 || patients > 1000) {
      found.count = "Enter a whole number from 1 to 1000.";
    }
    if (eta.trim() !== "") {
      const minutes = Number(eta);
      if (!Number.isInteger(minutes) || minutes < 0 || minutes > 1440) {
        found.eta = "Enter whole minutes from 0 to 1440, or leave blank.";
      }
    }
    setFieldError(found);
    if (!found.count && !found.eta) setReviewing(true);
  }

  async function send() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    const input: CreateHospitalNoticeInput = {
      hospital_id: chosen.id,
      patient_count: Number(count),
      severity: severity || null,
      eta_minutes: eta.trim() === "" ? null : Number(eta),
      clinical_notes: notes.trim() || null,
    };
    try {
      await api.createHospitalNotice(incident.id, input);
      onSent();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The notice could not be sent.");
      setReviewing(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-[var(--border)] p-3">
      <ErrorBanner message={error} />

      {!chosen && (
        <>
          <h3 className="text-sm font-semibold">Choose a hospital</h3>
          <p className="muted text-xs">
            Nearest first, within {RADIUS_KM} km, accepting emergencies and with a free bed. Bed
            counts are as last reported by the hospital.
          </p>
          {candidates === null && <p className="muted text-sm">Looking for hospitals…</p>}
          {candidates !== null && candidates.length === 0 && !error && (
            <p className="text-sm">
              No hospital within {RADIUS_KM} km is accepting patients with a free bed. Check the
              Hospitals screen, or phone one directly.
            </p>
          )}
          <ul className="space-y-2" aria-label="Nearby hospitals">
            {candidates?.map((hospital) => (
              <li key={hospital.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] p-2">
                <span className="text-sm">
                  <span className="font-medium">{hospital.name}</span>
                  <span className="muted block text-xs">
                    {hospital.distance_km.toFixed(1)} km · {hospital.available_beds} beds free ·{" "}
                    {hospital.icu_available} ICU free
                    {hospital.specialties.length > 0 ? ` · ${hospital.specialties.join(", ")}` : ""}
                  </span>
                </span>
                <Button variant="secondary" onClick={() => setChosen(hospital)}>
                  Choose
                </Button>
              </li>
            ))}
          </ul>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        </>
      )}

      {chosen && !reviewing && (
        <>
          <h3 className="text-sm font-semibold">Notice for {chosen.name}</h3>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Patients" error={fieldError.count}>
              <TextInput inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} />
            </Field>
            <Field label="ETA (minutes)" hint="Optional." error={fieldError.eta}>
              <TextInput inputMode="numeric" value={eta} onChange={(e) => setEta(e.target.value)} />
            </Field>
          </div>
          <Field label="Severity" hint="Leave blank to use the incident's own severity.">
            <select
              aria-label="Severity"
              className="surface w-full rounded-lg px-3 py-2.5 text-sm"
              value={severity}
              onChange={(e) => setSeverity(e.target.value as SeverityLevel | "")}
            >
              <option value="">Use the incident&apos;s</option>
              {SEVERITIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Clinical notes"
            hint="Only what the hospital needs to prepare. Do not paste the reporter's details."
          >
            <TextInput value={notes} maxLength={1000} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button onClick={review}>Review notice</Button>
            <Button variant="secondary" onClick={() => setChosen(null)}>
              Choose another
            </Button>
          </div>
        </>
      )}

      {chosen && reviewing && (
        <div role="group" aria-label="Confirm hospital notice" className="space-y-2">
          <p className="text-sm font-medium">
            Send {chosen.name} a notice of {count} patient{Number(count) === 1 ? "" : "s"}
            {eta.trim() ? `, ETA about ${eta} min` : ""}?
          </p>
          <p className="muted text-xs">
            It will include the incident category, severity, patient count, ETA and your clinical
            notes{notes.trim() ? `: “${notes.trim()}”` : " (none written)"}. It will not include the
            reporter, contact details, report text or location.
          </p>
          <div className="flex gap-2">
            <Button loading={busy} onClick={() => void send()}>
              Send notice
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => setReviewing(false)}>
              Back
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
