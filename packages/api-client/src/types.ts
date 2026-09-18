/**
 * Types mirroring the backend's Pydantic schemas.
 *
 * These are hand-maintained against `docs/API.md`. When an endpoint's contract
 * changes, this file changes in the same commit.
 */

export const USER_ROLES = [
  "CITIZEN",
  "RESPONDER",
  "DISPATCHER",
  "HOSPITAL_OPERATOR",
  "ADMIN",
  "SUPER_ADMIN",
] as const;
export type UserRole = (typeof USER_ROLES)[number];

/** Roles allowed to see the whole incident picture rather than only their own. */
export const OPERATIONAL_ROLES: readonly UserRole[] = [
  "RESPONDER",
  "DISPATCHER",
  "HOSPITAL_OPERATOR",
  "ADMIN",
  "SUPER_ADMIN",
];

/** Roles allowed to change incident state. */
export const DISPATCH_ROLES: readonly UserRole[] = [
  "DISPATCHER",
  "ADMIN",
  "SUPER_ADMIN",
];

export const INCIDENT_CATEGORIES = [
  "FLOOD",
  "FIRE",
  "ROAD_ACCIDENT",
  "MEDICAL",
  "BUILDING_COLLAPSE",
  "MISSING_PERSON",
  "LANDSLIDE",
  "INDUSTRIAL_ACCIDENT",
  "GAS_LEAK",
  "ELECTRICAL_HAZARD",
  "OTHER",
] as const;
export type IncidentCategory = (typeof INCIDENT_CATEGORIES)[number];

export const INCIDENT_STATUSES = [
  "REPORTED",
  "RECEIVED",
  "UNDER_REVIEW",
  "PRIORITIZED",
  "ASSIGNED",
  "RESPONDER_EN_ROUTE",
  "ON_SCENE",
  "RESOLVED",
  "CLOSED",
  "CANCELLED",
  "DUPLICATE",
  "REJECTED",
] as const;
export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];

export const OPEN_STATUSES: readonly IncidentStatus[] = [
  "REPORTED",
  "RECEIVED",
  "UNDER_REVIEW",
  "PRIORITIZED",
  "ASSIGNED",
  "RESPONDER_EN_ROUTE",
  "ON_SCENE",
];

export type SeverityLevel = "CRITICAL" | "HIGH" | "MODERATE" | "LOW";
export type PriorityBand = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface UserSummary {
  id: string;
  full_name: string;
  role: UserRole;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  user: User;
}

/** One contribution to a priority score, kept so the score can be explained. */
export interface PriorityFactor {
  key: string;
  label: string;
  points: number;
}

export interface IncidentSummary {
  id: string;
  reference_code: string;
  category: IncidentCategory;
  status: IncidentStatus;
  severity: SeverityLevel | null;
  priority_score: number | null;
  priority_band: PriorityBand | null;
  priority_overridden: boolean;
  latitude: string;
  longitude: string;
  address_text: string | null;
  people_affected: number | null;
  people_trapped: boolean;
  medical_required: boolean;
  immediate_danger: boolean;
  created_at: string;
  updated_at: string;
}

export interface Incident extends IncidentSummary {
  description: string;
  landmark: string | null;
  location_accuracy_m: number | null;
  contact_phone: string | null;
  priority_factors: PriorityFactor[] | null;
  priority_override_reason: string | null;
  reported_by: UserSummary | null;
  assigned_to: UserSummary | null;
  duplicate_of_id: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  media: MediaItem[];
}

export interface MediaItem {
  id: string;
  incident_id: string;
  media_type: "IMAGE" | "AUDIO" | "VIDEO";
  content_type: string;
  size_bytes: number;
  original_filename: string | null;
  created_at: string;
}

export interface StatusHistoryEntry {
  id: string;
  from_status: IncidentStatus | null;
  to_status: IncidentStatus;
  note: string | null;
  created_at: string;
  changed_by: UserSummary | null;
}

export interface IncidentStats {
  total_open: number;
  by_band: Record<string, number>;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  unassigned_open: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CreateIncidentInput {
  category: IncidentCategory;
  description: string;
  latitude: number;
  longitude: number;
  location_accuracy_m?: number | null;
  address_text?: string | null;
  landmark?: string | null;
  people_affected?: number | null;
  people_trapped: boolean;
  medical_required: boolean;
  immediate_danger: boolean;
  contact_phone?: string | null;
}

export interface IncidentQuery {
  page?: number;
  page_size?: number;
  status?: IncidentStatus[];
  category?: IncidentCategory[];
  priority_band?: PriorityBand;
  q?: string;
  open_only?: boolean;
  assigned_to_me?: boolean;
  sort?: "priority" | "created_at" | "-created_at";
}

export interface GeoFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    reference_code: string;
    category: IncidentCategory;
    status: IncidentStatus;
    priority_band: PriorityBand | null;
    priority_score: number | null;
    people_affected: number | null;
    people_trapped: boolean;
    created_at: string;
  };
}

export interface GeoFeatureCollection {
  type: "FeatureCollection";
  features: GeoFeature[];
  count: number;
  truncated: boolean;
}

/** The backend's error envelope, as documented in `docs/API.md`. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}
