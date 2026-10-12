import type { GlobeMarker } from "@/components/3d/IncidentMarker";

/**
 * DEMONSTRATION DATA — not incidents, not live, not from the backend.
 *
 * The landing page is public and has no session, so it cannot show real
 * incidents. These are real city coordinates with illustrative priority bands,
 * used only to show what the marker and arc visuals look like. The page labels
 * them as such. Signed-in views draw real incidents from the API instead.
 */
export const DEMO_MARKERS: GlobeMarker[] = [
  { id: "demo-delhi", lat: 28.6139, lon: 77.209, band: "CRITICAL", label: "Delhi" },
  { id: "demo-mumbai", lat: 19.076, lon: 72.8777, band: "HIGH", label: "Mumbai" },
  { id: "demo-kolkata", lat: 22.5726, lon: 88.3639, band: "MEDIUM", label: "Kolkata" },
  { id: "demo-hyderabad", lat: 17.385, lon: 78.4867, band: "LOW", label: "Hyderabad" },
  { id: "demo-bengaluru", lat: 12.9716, lon: 77.5946, band: "MEDIUM", label: "Bengaluru" },
  { id: "demo-chennai", lat: 13.0827, lon: 80.2707, band: "HIGH", label: "Chennai" },
];

export const DEMO_ARCS = [
  { from: "demo-delhi", to: "demo-mumbai" },
  { from: "demo-delhi", to: "demo-kolkata" },
  { from: "demo-mumbai", to: "demo-bengaluru" },
  { from: "demo-hyderabad", to: "demo-chennai" },
  { from: "demo-kolkata", to: "demo-chennai" },
];
