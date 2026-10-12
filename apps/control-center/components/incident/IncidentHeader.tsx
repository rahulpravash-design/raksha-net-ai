import {
  categoryLabel,
  formatRelative,
  type Incident,
} from "@raksha/api-client";

import { PriorityBadge, StatusBadge } from "@/components/ui";

function Chip({ glyph, children, tone }: { glyph: string; children: string; tone?: "alert" }) {
  return (
    <li
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${
        tone === "alert"
          ? "border-red-400/50 bg-red-500/10 text-red-200"
          : "border-[var(--border)]"
      }`}
    >
      <span aria-hidden="true">{glyph}</span>
      {children}
    </li>
  );
}

/**
 * The first thing a dispatcher reads: what, how urgent, in what state, and the
 * handful of facts that change how they act. Every fact is the reporter's claim
 * or an operator's entry; none is AI output (that has its own panel).
 */
export function IncidentHeader({ incident }: { incident: Incident }) {
  return (
    <header className="panel-3d space-y-3 rounded-xl p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{categoryLabel(incident.category)}</h1>
        <StatusBadge status={incident.status} />
        <PriorityBadge band={incident.priority_band} />
        {incident.priority_score !== null && (
          <span className="muted text-sm tabular-nums">
            engine score {incident.priority_score}
            {incident.priority_overridden ? " · overridden by an operator" : ""}
          </span>
        )}
        <span className="muted ml-auto font-mono text-sm">{incident.reference_code}</span>
      </div>

      <ul className="flex flex-wrap gap-2" aria-label="Key facts">
        {incident.people_trapped && (
          <Chip glyph="⚠" tone="alert">
            People trapped
          </Chip>
        )}
        {incident.immediate_danger && (
          <Chip glyph="⚠" tone="alert">
            Immediate danger
          </Chip>
        )}
        {incident.medical_required && <Chip glyph="＋">Medical support required</Chip>}
        {incident.people_affected !== null && (
          <Chip glyph="●">{`${incident.people_affected} affected`}</Chip>
        )}
        <Chip glyph="◷">{`Reported ${formatRelative(incident.created_at)}`}</Chip>
        <Chip glyph="◉">
          {incident.assigned_to
            ? `Assigned to ${incident.assigned_to.full_name}`
            : "Not assigned to an operator"}
        </Chip>
      </ul>
    </header>
  );
}
