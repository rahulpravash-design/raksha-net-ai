"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";

import {
  categoryLabel,
  formatRelative,
  resourceStatusLabel,
  resourceTypeLabel,
  statusLabel,
  type GeoFeature,
  type Resource,
} from "@raksha/api-client";

import { clusterPoints } from "@/lib/cluster";
import { MAP_DEFAULTS, MAP_TILES } from "@/lib/config";
import { priorityTheme } from "@/lib/theme";

import { clusterIcon, incidentIcon, resourceIcon } from "./maps/markerIcons";

export interface Viewport {
  minLat: number;
  minLon: number;
  maxLat: number;
  maxLon: number;
}

/**
 * Report the visible bounds upwards, so the parent fetches only what is on
 * screen rather than every incident in the region. Also reports the zoom, which
 * decides how markers are clustered.
 */
function ViewState({
  onChange,
  onZoom,
}: {
  onChange: (bounds: Viewport) => void;
  onZoom: (zoom: number) => void;
}) {
  const map = useMapEvents({
    moveend: () => report(),
    zoomend: () => report(),
  });

  function report() {
    const bounds = map.getBounds();
    onZoom(map.getZoom());
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

export default function IncidentMap({
  features,
  resources = [],
  showResources = false,
  selectedId,
  onViewportChange,
  onSelect,
}: {
  features: GeoFeature[];
  resources?: Resource[];
  showResources?: boolean;
  selectedId: string | null;
  onViewportChange: (bounds: Viewport) => void;
  onSelect: (id: string) => void;
}) {
  const [zoom, setZoom] = useState<number>(MAP_DEFAULTS.zoom);

  const selected = useMemo(
    () => features.find((feature) => feature.id === selectedId) ?? null,
    [features, selectedId],
  );

  const byId = useMemo(() => new Map(features.map((f) => [f.id, f])), [features]);

  const clusters = useMemo(
    () =>
      clusterPoints(
        features.map((f) => ({
          id: f.id,
          lat: f.geometry.coordinates[1],
          lon: f.geometry.coordinates[0],
          band: f.properties.priority_band,
        })),
        zoom,
      ),
    [features, zoom],
  );

  return (
    <MapContainer
      center={[MAP_DEFAULTS.centre.latitude, MAP_DEFAULTS.centre.longitude]}
      zoom={MAP_DEFAULTS.zoom}
      scrollWheelZoom
      className="h-full w-full rounded-xl"
    >
      <TileLayer url={MAP_TILES.url} attribution={MAP_TILES.attribution} />
      <ViewState onChange={onViewportChange} onZoom={setZoom} />
      <SelectionFocus feature={selected} />

      {showResources &&
        resources.map((resource) => (
          <Marker
            key={resource.id}
            position={[Number(resource.latitude), Number(resource.longitude)]}
            icon={resourceIcon(resource.resource_type, resource.status)}
            title={`${resource.call_sign} — ${resourceTypeLabel(resource.resource_type)}, ${resourceStatusLabel(resource.status)}`}
            alt={`${resource.call_sign}, ${resourceStatusLabel(resource.status)}`}
            zIndexOffset={-100}
          >
            <Popup>
              <div className="space-y-1 text-sm">
                <p className="font-semibold">
                  {resource.call_sign} · {resource.name}
                </p>
                <p>
                  {resourceTypeLabel(resource.resource_type)} ·{" "}
                  {resourceStatusLabel(resource.status)}
                </p>
                {resource.capabilities.length > 0 && (
                  <p className="text-xs">Capabilities: {resource.capabilities.join(", ")}</p>
                )}
              </div>
            </Popup>
          </Marker>
        ))}

      {clusters.map((cluster) => {
        const single = cluster.count === 1 ? byId.get(cluster.ids[0] ?? "") : undefined;

        if (!single) {
          return (
            <Marker
              key={`c-${cluster.key}`}
              position={[cluster.lat, cluster.lon]}
              icon={clusterIcon(cluster.count, cluster.band)}
              title={`${cluster.count} incidents, most urgent: ${priorityTheme(cluster.band).label}`}
              alt={`${cluster.count} incidents`}
              eventHandlers={{
                // Zoom in on the group rather than opening a popup of many.
                click: (event) => event.target._map.setView([cluster.lat, cluster.lon], zoom + 2),
              }}
            />
          );
        }

        const { properties } = single;
        const theme = priorityTheme(properties.priority_band);
        const label = `${theme.label} priority ${categoryLabel(properties.category)} ${properties.reference_code}`;
        return (
          <Marker
            key={single.id}
            position={[single.geometry.coordinates[1], single.geometry.coordinates[0]]}
            icon={incidentIcon(properties.priority_band, single.id === selectedId)}
            title={label}
            alt={label}
            eventHandlers={{ click: () => onSelect(single.id) }}
          >
            <Popup>
              <div className="space-y-1 text-sm">
                <p className="font-semibold">{categoryLabel(properties.category)}</p>
                <p className="font-mono text-xs">{properties.reference_code}</p>
                <p>
                  <span aria-hidden="true" style={{ color: theme.hex }}>
                    {theme.glyph}
                  </span>{" "}
                  {theme.label} · {statusLabel(properties.status)}
                </p>
                {properties.people_trapped && (
                  <p className="font-semibold text-red-400">People trapped</p>
                )}
                <p className="text-xs">{formatRelative(properties.created_at)}</p>
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
