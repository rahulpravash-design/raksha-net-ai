import { canViewIncidents, type UserRole } from "@raksha/api-client";

/**
 * Where a signed-in user lands. A hospital operator has no business on the
 * incident queue (the API refuses it — they see hospitals and their own inbound
 * notices only), so their home is the hospitals screen. Responders are not
 * admitted to the control centre at all (see `lib/admission.ts`).
 */
export function homeFor(role: UserRole, mustChangePassword = false): string {
  // An administrator-set password has to be replaced before anything else works.
  if (mustChangePassword) return "/account/security";
  return role === "HOSPITAL_OPERATOR" ? "/hospitals" : "/dashboard";
}

/** Whether the role may read incident records — the dispatch side only. */
export function seesIncidents(role: UserRole): boolean {
  return canViewIncidents(role);
}
