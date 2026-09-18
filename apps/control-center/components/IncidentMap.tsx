"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo } from "react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";

import {
  bandStyle,
  categoryLabel,
  formatRelative,
  statusLabel,
  type GeoFeature,
} from "@raksha/api-client";

import { MAP_DEFAULTS, MAP_TILES } from "@/lib/config";

export interface Viewport {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

/**
 * Report the visible bounds upwards, so the parent fetches only what is on
 * screen rather than every incident in the region.
 */
function ViewportReporter({ onChange }: { onChange: (bounds: Viewport) => void }) {
  const map = useMapEvents({
    moveend: () => report(),
    zoomend: () => report(),
  });

  function report() {
    const bounds = map.getBounds();
    onChange({
      minLat: bounds.getSouth(),
      minLon: bounds.getWest(),
      maxLat: bounds.getNorth(),
      maxLon: bounds.getEast(),
    });
  }

  useEffect(() => {
    report();
    // Only on mount: afterwards the map events drive the updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

/** Pans to a selected incident without fighting the operator's own panning. */
function SelectionFocus({ feature }: { feature: GeoFeature | null }) {
  const map = useMap();

  useEffect(() => {
    if (!feature) return;
    const [longitude, latitude] = feature.geometry.coordinates;
    map.panTo(L.latLng(latitude, longitude), { animate: true });
  }, [feature, map]);

  return null;
}

/** Marker radius grows with urgency, so the map reads without the legend. */
function radiusFor(feature: GeoFeature): number {
  switch (feature.properties.priority_band) {
    case "CRITICAL":
      return 12;
    case "HIGH":
      return 10;
    case "MEDIUM":
      return 8;
    default:
      return 6;
  }
}

export default function IncidentMap({
  features,
  selectedId,
  onViewportChange,
  onSelect,
}: {
  features: GeoFeature[];
  selectedId: string | null;
  onViewportChange: (bounds: Viewport) => void;
  onSelect: (id: string) => void;
}) {
  const selected = useMemo(
    () => features.find((feature) => feature.id === selectedId) ?? null,
    [features, selectedId],
  );

  return (
    <MapContainer
      center={[MAP_DEFAULTS.centre.latitude, MAP_DEFAULTS.centre.longitude]}
      zoom={MAP_DEFAULTS.zoom}
      scrollWheelZoom
      className="h-full w-full rounded-xl"
    >
      <TileLayer url={MAP_TILES.url} attribution={MAP_TILES.attribution} />
      <ViewportReporter onChange={onViewportChange} />
      <SelectionFocus feature={selected} />

      {features.map((feature) => {
        const [longitude, latitude] = feature.geometry.coordinates;
        const style = bandStyle(feature.properties.priority_band);
        const isSelected = feature.id === selectedId;

        return (
          <CircleMarker
            key={feature.id}
            center={[latitude, longitude]}
            radius={radiusFor(feature)}
            pathOptions={{
              color: isSelected ? "#0f172a" : style.marker,
              weight: isSelected ? 3 : 1.5,
              fillColor: style.marker,
              fillOpacity: 0.75,
            }}
            eventHandlers={{ click: () => onSelect(feature.id) }}
          >
            <Popup>
              <div className="space-y-1 text-sm">
                <p className="font-semibold">
                  {categoryLabel(feature.properties.category)}
                </p>
                <p className="font-mono text-xs">
                  {feature.properties.reference_code}
                </p>
                <p>
                  {style.label} · {statusLabel(feature.properties.status)}
                </p>
                {feature.properties.people_trapped && (
                  <p className="font-semibold text-red-700">People trapped</p>
                )}
                <p className="text-xs">
                  {formatRelative(feature.properties.created_at)}
                </p>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
