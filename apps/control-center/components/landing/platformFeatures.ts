import type { PlatformFeature } from "@/lib/landing";

/**
 * The platform's screens, described only as they exist today. Each `href` is a
 * real route (tests/landing.test.ts walks `app/` to prove it), and each summary
 * states what the screen does and where a human stays in control.
 */
export const PLATFORM_FEATURES: PlatformFeature[] = [
  {
    id: "dashboard",
    title: "Live incident dashboard",
    summary:
      "Open reports ranked by the deterministic priority engine, with the factors behind each score. It refreshes every 15 seconds and says so when the connection drops.",
    href: "/dashboard",
    audience: "dispatch",
    audienceLabel: "Dispatch staff",
  },
  {
    id: "map",
    title: "Interactive map",
    summary:
      "Incidents and response units on OpenStreetMap, with a Map ⇄ Globe toggle. Priority is always a symbol and a word as well as a colour.",
    href: "/dashboard",
    audience: "dispatch",
    audienceLabel: "Dispatch staff",
  },
  {
    id: "ai",
    title: "AI analysis panel",
    summary:
      "On each incident: what the AI read from the report, labelled as AI-derived with its model, version and confidence. An observation is never a fact, and a person accepts, edits or rejects it. With the AI service off, reports are still triaged by people.",
    href: "/dashboard",
    audience: "dispatch",
    audienceLabel: "Dispatch staff · open any incident",
  },
  {
    id: "resources",
    title: "Resource dashboard",
    summary:
      "Units with status, position and capabilities. The nearest suitable unit is suggested with its reasons; only a dispatcher can send it.",
    href: "/resources",
    audience: "dispatch",
    audienceLabel: "Dispatch staff",
  },
  {
    id: "analytics",
    title: "Response analytics",
    summary:
      "How long reports take to be answered and resolved, by category and by resource type, with incident hotspots drawn on coarsened coordinates — never a report's exact position.",
    href: "/analytics",
    audience: "dispatch",
    audienceLabel: "Dispatch staff",
  },
  {
    id: "hospitals",
    title: "Hospital interface",
    summary:
      "Bed and ICU capacity, and inbound-patient notices. A hospital operator sees the minimised notice — ETA and clinical notes — never the reporter's details.",
    href: "/hospitals",
    audience: "console",
    audienceLabel: "Dispatch staff and hospital operators",
  },
];
