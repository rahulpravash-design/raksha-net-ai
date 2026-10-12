import { formatCoordinates, formatDateTime, type Incident } from "@raksha/api-client";

/** The reported situation: the reporter's words and the facts they supplied. */
export function SituationBody({ incident }: { incident: Incident }) {
  return (
    <>
      <blockquote className="border-l-2 border-[var(--accent)]/50 pl-3 text-sm whitespace-pre-wrap">
        {incident.description}
      </blockquote>
      <p className="muted mt-2 text-xs">
        The reporter&apos;s own words, unedited. Facts below are as reported, not
        independently verified.
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="muted">People affected</dt>
          <dd className="font-medium">{incident.people_affected ?? "Unknown"}</dd>
        </div>
        <div>
          <dt className="muted">Trapped</dt>
          <dd className="font-medium">{incident.people_trapped ? "Yes" : "Not reported"}</dd>
        </div>
        <div>
          <dt className="muted">Medical support</dt>
          <dd className="font-medium">{incident.medical_required ? "Required" : "Not reported"}</dd>
        </div>
        <div>
          <dt className="muted">Immediate danger</dt>
          <dd className="font-medium">{incident.immediate_danger ? "Yes" : "Not reported"}</dd>
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
    </>
  );
}

/** Where it is, and how far to trust the position. */
export function LocationBody({ incident }: { incident: Incident }) {
  const approximate =
    incident.location_accuracy_m !== null && incident.location_accuracy_m > 100;
  return (
    <>
      <p className="font-mono text-sm">
        {formatCoordinates(incident.latitude, incident.longitude)}
      </p>
      {incident.location_accuracy_m !== null && (
        <p className={approximate ? "mt-1 text-sm text-amber-300" : "muted mt-1 text-sm"}>
          Device accuracy about {incident.location_accuracy_m} m
          {approximate ? " — treat as approximate." : ""}
        </p>
      )}
      {incident.address_text && <p className="mt-1 text-sm">{incident.address_text}</p>}
      {incident.landmark && <p className="mt-1 text-sm">Landmark: {incident.landmark}</p>}
    </>
  );
}
