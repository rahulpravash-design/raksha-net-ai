import L from "leaflet";

import type { PriorityBand, ResourceStatus, ResourceType } from "@raksha/api-client";

import { RESOURCE_STATUS_COLOR, priorityTheme } from "@/lib/theme";

/** Distinct silhouettes per band, so priority survives without colour vision. */
function shape(band: PriorityBand | null, color: string): string {
  switch (band) {
    case "CRITICAL":
      return `<polygon points="12,2 23,21 1,21" fill="${color}" stroke="#050914" stroke-width="1.5"/>`;
    case "HIGH":
      return `<polygon points="12,1 23,12 12,23 1,12" fill="${color}" stroke="#050914" stroke-width="1.5"/>`;
    case "MEDIUM":
      return `<rect x="3" y="3" width="18" height="18" rx="2" fill="${color}" stroke="#050914" stroke-width="1.5"/>`;
    case "LOW":
      return `<circle cx="12" cy="12" r="9" fill="${color}" stroke="#050914" stroke-width="1.5"/>`;
    default:
      return `<circle cx="12" cy="12" r="8" fill="none" stroke="${color}" stroke-width="2.5"/>`;
  }
}

export function incidentIcon(band: PriorityBand | null, selected: boolean): L.DivIcon {
  const { hex } = priorityTheme(band);
  const size = band === "CRITICAL" ? 30 : band === "HIGH" ? 27 : 24;
  const pulse = band === "CRITICAL" || selected ? "raksha-pulse" : "";
  const halo = selected
    ? `<span style="position:absolute;inset:-5px;border:2px solid #f2f7ff;border-radius:9999px"></span>`
    : "";
  return L.divIcon({
    className: "raksha-marker",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<span class="${pulse}" style="position:relative;display:block;width:${size}px;height:${size}px;color:${hex}">${halo}<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${shape(band, hex)}</svg></span>`,
  });
}

export function clusterIcon(count: number, band: PriorityBand | null): L.DivIcon {
  const { hex } = priorityTheme(band);
  return L.divIcon({
    className: "raksha-marker",
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    html: `<span style="display:flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:9999px;background:#0e192a;border:3px solid ${hex};color:#f2f7ff;font:700 13px system-ui">${count}</span>`,
  });
}

const RESOURCE_ABBR: Record<ResourceType, string> = {
  AMBULANCE: "AMB",
  FIRE_ENGINE: "FIRE",
  RESCUE_TEAM: "RES",
  POLICE_UNIT: "POL",
  RESCUE_BOAT: "BOAT",
  SHELTER: "SHL",
  OTHER_RESOURCE: "OTH",
};

export function resourceAbbreviation(type: ResourceType): string {
  return RESOURCE_ABBR[type] ?? "OTH";
}


export function resourceIcon(type: ResourceType, status: ResourceStatus): L.DivIcon {
  const color = RESOURCE_STATUS_COLOR[status];
  const dashed = status === "OUT_OF_SERVICE" ? "dashed" : "solid";
  return L.divIcon({
    className: "raksha-marker",
    iconSize: [38, 22],
    iconAnchor: [19, 11],
    html: `<span style="display:flex;align-items:center;justify-content:center;width:38px;height:22px;border-radius:6px;background:#0e192a;border:2px ${dashed} ${color};color:${color};font:700 10px system-ui;letter-spacing:.04em">${resourceAbbreviation(type)}</span>`,
  });
}
