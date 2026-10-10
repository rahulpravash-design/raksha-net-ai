import { categoryLabel, type IncidentSummary } from "@raksha/api-client";

import type { GlobeMarker } from "@/components/3d/IncidentMarker";

/**
 * Real incidents as globe markers. One incident, one marker: nothing is added,
 * averaged or invented. A record whose coordinates are not finite numbers is left
 * out rather than drawn at (0, 0).
 */
export function incidentMarkers(incidents: IncidentSummary[]): GlobeMarker[] {
  return incidents.flatMap((incident) => {
    const lat = Number(incident.latitude);
    const lon = Number(incident.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return [];
    return [
      {
        id: incident.id,
        lat,
        lon,
        band: incident.priority_band,
        label: `${categoryLabel(incident.category)} ${incident.reference_code}`,
      },
    ];
  });
}
