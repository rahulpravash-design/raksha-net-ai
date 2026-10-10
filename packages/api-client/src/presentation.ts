/**
 * Presentation helpers shared by every front end.
 *
 * Priority colour is defined once, here, so a CRITICAL incident cannot look
 * like one thing in the citizen app and another in the control centre.
 */

import type {
  HospitalNoticeStatus,
  DispatchStatus,
  IncidentCategory,
  IncidentStatus,
  PriorityBand,
  ResourceStatus,
  ResourceType,
  UserRole,
} from "./types";
import { DISPATCH_ROLES, OPERATIONAL_ROLES } from "./types";

export interface BandStyle {
  /** Tailwind classes for a filled badge. */
  badge: string;
  /** Tailwind classes for a left border accent on a list row. */
  accent: string;
  /** Hex colour for a map marker, where Tailwind classes cannot reach. */
  marker: string;
  label: string;
}

/**
 * Colour is never the only signal: each band also carries its own text label,
 * so the meaning survives for a colour-blind operator or a greyscale printout.
 */
export const BAND_STYLES: Record<PriorityBand, BandStyle> = {
  CRITICAL: {
    badge: "bg-red-600 text-white",
    accent: "border-l-red-600",
    marker: "#dc2626",
    label: "Critical",
  },
  HIGH: {
    badge: "bg-orange-500 text-white",
    accent: "border-l-orange-500",
    marker: "#f97316",
    label: "High",
  },
  MEDIUM: {
    badge: "bg-amber-400 text-amber-950",
    accent: "border-l-amber-400",
    marker: "#fbbf24",
    label: "Medium",
  },
  LOW: {
    badge: "bg-emerald-600 text-white",
    accent: "border-l-emerald-600",
    marker: "#059669",
    label: "Low",
  },
};

export const UNSCORED_BAND_STYLE: BandStyle = {
  badge: "bg-slate-300 text-slate-900",
  accent: "border-l-slate-300",
  marker: "#94a3b8",
  label: "Not scored",
};

export function bandStyle(band: PriorityBand | null): BandStyle {
  return band ? BAND_STYLES[band] : UNSCORED_BAND_STYLE;
}

const CATEGORY_LABELS: Record<IncidentCategory, string> = {
  FLOOD: "Flood",
  FIRE: "Fire",
  ROAD_ACCIDENT: "Road accident",
  MEDICAL: "Medical emergency",
  BUILDING_COLLAPSE: "Building collapse",
  MISSING_PERSON: "Missing person",
  LANDSLIDE: "Landslide",
  INDUSTRIAL_ACCIDENT: "Industrial accident",
  GAS_LEAK: "Gas leak",
  ELECTRICAL_HAZARD: "Electrical hazard",
  OTHER: "Other",
};

export function categoryLabel(category: IncidentCategory): string {
  return CATEGORY_LABELS[category] ?? category;
}

const STATUS_LABELS: Record<IncidentStatus, string> = {
  REPORTED: "Reported",
  RECEIVED: "Received",
  UNDER_REVIEW: "Under review",
  PRIORITIZED: "Prioritised",
  ASSIGNED: "Assigned",
  RESPONDER_EN_ROUTE: "Responder en route",
  ON_SCENE: "On scene",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
  DUPLICATE: "Duplicate",
  REJECTED: "Rejected",
};

export function statusLabel(status: IncidentStatus): string {
  return STATUS_LABELS[status] ?? status;
}

/** Plain-language status text for the person who filed the report. */
const CITIZEN_STATUS_MESSAGES: Record<IncidentStatus, string> = {
  REPORTED: "Your report has been received and is waiting to be reviewed.",
  RECEIVED: "The control centre has your report.",
  UNDER_REVIEW: "An operator is reviewing your report now.",
  PRIORITIZED: "Your report has been prioritised and is awaiting assignment.",
  ASSIGNED: "A response team has been assigned.",
  RESPONDER_EN_ROUTE: "A response team is on the way.",
  ON_SCENE: "The response team has arrived at the location.",
  RESOLVED: "The incident has been resolved.",
  CLOSED: "This report is now closed.",
  CANCELLED: "This report was cancelled.",
  DUPLICATE: "This was recorded as a duplicate of another report.",
  REJECTED: "This report was not accepted by the control centre.",
};

export function citizenStatusMessage(status: IncidentStatus): string {
  return CITIZEN_STATUS_MESSAGES[status] ?? statusLabel(status);
}

const NOTICE_STATUS_LABELS: Record<HospitalNoticeStatus, string> = {
  NOTIFIED: "Notified — awaiting the hospital",
  ACKNOWLEDGED: "Acknowledged",
  ARRIVED: "Patient arrived",
  DIVERTED: "Diverted",
  CANCELLED: "Cancelled",
};

export function hospitalNoticeStatusLabel(value: HospitalNoticeStatus): string {
  return NOTICE_STATUS_LABELS[value] ?? value;
}

/** Mirrors the backend's notice transition table; the server remains the authority. */
export const NEXT_NOTICE_STATUSES: Record<HospitalNoticeStatus, HospitalNoticeStatus[]> = {
  NOTIFIED: ["ACKNOWLEDGED", "DIVERTED", "CANCELLED"],
  ACKNOWLEDGED: ["ARRIVED", "DIVERTED", "CANCELLED"],
  ARRIVED: [],
  DIVERTED: [],
  CANCELLED: [],
};

export function isOperationalRole(role: UserRole): boolean {
  return OPERATIONAL_ROLES.includes(role);
}

export function canDispatch(role: UserRole): boolean {
  return DISPATCH_ROLES.includes(role);
}

/** Absolute time, rendered in the viewer's locale. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/**
 * Relative time for a queue that is scanned rather than read.
 *
 * `now` is a parameter so the output is deterministic under test and so a
 * server render and the client hydration agree.
 */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "—";

  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return `${seconds}s ago`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ${minutes % 60} min ago`;

  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

/** Coordinates as an operator reads them aloud. */
export function formatCoordinates(
  latitude: string | number,
  longitude: string | number,
): string {
  const lat = Number(latitude);
  const lon = Number(longitude);
  if (Number.isNaN(lat) || Number.isNaN(lon)) return "—";
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

export type ConfidenceTier = "high" | "medium" | "low";

/**
 * The confidence policy from `docs/AI_ARCHITECTURE.md` section 5: a high
 * confidence may be shown pre-filled for one-click acceptance, a medium one
 * shown but not pre-filled, and a low or missing confidence shown as a
 * de-emphasised hint. A missing confidence is treated as low, never as
 * certainty — the same rule `ai.common.validation.is_low_confidence` applies
 * on the backend.
 */
export function confidenceTier(confidence: number | null): ConfidenceTier {
  if (confidence === null) return "low";
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.6) return "medium";
  return "low";
}

export function formatConfidence(confidence: number | null): string {
  if (confidence === null) return "unknown confidence";
  return `${Math.round(confidence * 100)}% confidence`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  AMBULANCE: "Ambulance",
  FIRE_ENGINE: "Fire engine",
  RESCUE_TEAM: "Rescue team",
  POLICE_UNIT: "Police unit",
  RESCUE_BOAT: "Rescue boat",
  SHELTER: "Shelter",
  OTHER_RESOURCE: "Other",
};

export function resourceTypeLabel(value: ResourceType): string {
  return RESOURCE_TYPE_LABELS[value] ?? value;
}

const RESOURCE_STATUS_LABELS: Record<ResourceStatus, string> = {
  AVAILABLE: "Available",
  DISPATCHED: "Dispatched",
  EN_ROUTE: "En route",
  ON_SCENE: "On scene",
  OUT_OF_SERVICE: "Out of service",
};

export function resourceStatusLabel(value: ResourceStatus): string {
  return RESOURCE_STATUS_LABELS[value] ?? value;
}

const DISPATCH_STATUS_LABELS: Record<DispatchStatus, string> = {
  DISPATCHED: "Dispatched",
  ACKNOWLEDGED: "Acknowledged",
  EN_ROUTE: "En route",
  ON_SCENE: "On scene",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
};

export function dispatchStatusLabel(value: DispatchStatus): string {
  return DISPATCH_STATUS_LABELS[value] ?? value;
}

/**
 * The next steps a crew can report from where they are.
 *
 * Mirrors the backend's transition table so the app offers only legal moves.
 * The backend remains the authority; this just avoids showing a button that
 * can only fail.
 */
export const NEXT_DISPATCH_STATUSES: Record<DispatchStatus, DispatchStatus[]> =
  {
    DISPATCHED: ["ACKNOWLEDGED", "EN_ROUTE", "CANCELLED"],
    ACKNOWLEDGED: ["EN_ROUTE", "CANCELLED"],
    EN_ROUTE: ["ON_SCENE", "CANCELLED"],
    ON_SCENE: ["COMPLETED", "CANCELLED"],
    COMPLETED: [],
    CANCELLED: [],
  };
