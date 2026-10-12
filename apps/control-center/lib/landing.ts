import { canViewIncidents, isConsoleRole, type User, type UserRole } from "@raksha/api-client";

import { homeFor } from "@/lib/routes";

/**
 * What the globe on the landing page is showing, and therefore what the page
 * may claim about it.
 *
 * - `checking` — the session is still being read. Nothing is drawn: showing the
 *   demonstration markers for a moment and then swapping them would put
 *   made-up locations in front of a signed-in operator.
 * - `live` — a signed-in dispatch-side user: the markers are the platform's open
 *   incidents.
 * - `demo` — everyone else. The public page has no session, so it can show only
 *   labelled demonstration markers. Real incident locations never go to an
 *   anonymous visitor (CLAUDE.md section 5).
 */
export type GlobeMode = "checking" | "live" | "demo";

export function globeMode(user: User | null, authLoading: boolean): GlobeMode {
  if (authLoading) return "checking";
  return user && canViewIncidents(user.role) ? "live" : "demo";
}

/** The primary call to action for whoever is looking at the page. */
export function primaryAction(user: User | null): { href: string; label: string } {
  if (!user) return { href: "/dashboard", label: "ENTER COMMAND CENTER" };
  const href = homeFor(user.role, user.must_change_password);
  if (user.must_change_password) return { href, label: "SET A NEW PASSWORD" };
  return {
    href,
    label: user.role === "HOSPITAL_OPERATOR" ? "OPEN HOSPITALS" : "ENTER COMMAND CENTER",
  };
}

export type FeatureAccess = "open" | "sign-in" | "not-for-role";

export interface PlatformFeature {
  id: string;
  title: string;
  summary: string;
  /** An existing screen. A test checks that every one has a page. */
  href: string;
  /** `dispatch`: the dispatch side. `console`: also hospital operators. */
  audience: "dispatch" | "console";
  audienceLabel: string;
}

/** Whether the visitor can open a feature, must sign in first, or never could. */
export function featureAccess(feature: PlatformFeature, role: UserRole | null): FeatureAccess {
  if (role === null) return "sign-in";
  const allowed = feature.audience === "dispatch" ? canViewIncidents(role) : isConsoleRole(role);
  return allowed ? "open" : "not-for-role";
}
