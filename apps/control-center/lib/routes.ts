import type { UserRole } from "@raksha/api-client";

/**
 * Where a signed-in user lands. A hospital operator has no business on the
 * incident queue (the API refuses it — they see hospitals and their own inbound
 * notices only), so their home is the hospitals screen.
 */
export function homeFor(role: UserRole): string {
  return role === "HOSPITAL_OPERATOR" ? "/hospitals" : "/dashboard";
}

export function seesIncidents(role: UserRole): boolean {
  return role !== "HOSPITAL_OPERATOR";
}
