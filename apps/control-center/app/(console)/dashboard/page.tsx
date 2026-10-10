"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  INCIDENT_CATEGORIES,
  categoryLabel,
  type GeoFeature,
  type IncidentCategory,
  type IncidentStats,
  type IncidentSummary,
  type PriorityBand,
  type Resource,
} from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import { GlobeStage } from "@/components/3d/GlobeStage";
import { Reveal } from "@/components/animations/Reveal";
import { ActivityTimeline } from "@/components/command-center/ActivityTimeline";
import { CommandStrip } from "@/components/command-center/CommandStrip";
import {
  SelectedIncident,
  useSelectedIncident,
} from "@/components/command-center/SelectedIncident";
import { IncidentQueue } from "@/components/IncidentQueue";
import { MapControls, type MapView } from "@/components/maps/MapControls";
import { MapLegend } from "@/components/maps/MapLegend";
import { StatsBar } from "@/components/StatsBar";
import { ErrorBanner, Spinner, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import { MAP_DEFAULTS } from "@/lib/config";
import type { Viewport } from "@/components/IncidentMap";

// Leaflet reaches for `window` at import time, so the map is client-only.
const IncidentMap = dynamic(() => import("@/components/IncidentMap"), {
  ssr: false,
  loading: () => (
    <div className="surface flex h-full items-center justify-center rounded-xl">
      <Spinner label="Loading map" />
    </div>
  ),
});

/**
 * Polling interval for the live queue.
 *
 * V1 polls rather than holding a socket: it is simpler, survives a reconnect
 * without special handling, and is adequate at pilot scale. The WebSocket
 * upgrade is specified in docs/API.md for Phase 5.
 */
const REFRESH_MS = 15_000;

// The globe opens facing the configured map centre.
const MAP_FOCUS_LON = MAP_DEFAULTS.centre.longitude;

const BANDS: PriorityBand[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function DashboardPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [stats, setStats] = useState<IncidentStats | null>(null);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [features, setFeatures] = useState<GeoFeature[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [view, setView] = useState<MapView>("map");
  const [showResources, setShowResources] = useState(true);
  const [connected, setConnected] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [initialised, setInitialised] = useState(false);

  const [search, setSearch] = useState("");
  const [band, setBand] = useState<PriorityBand | "">("");
  const [category, setCategory] = useState<IncidentCategory | "">("");

  // Held in a ref so a map pan does not re-create the polling effect.
  const viewportRef = useRef<Viewport | null>(null);

  const loadQueue = useCallback(async () => {
    try {
      const [page, summary] = await Promise.all([
        api.incidentQueue({
          open_only: true,
          sort: "priority",
          page_size: 50,
          ...(search.trim() ? { q: search.trim() } : {}),
          ...(band ? { priority_band: band } : {}),
          ...(category ? { category: [category] } : {}),
        }),
        api.incidentStats(),
      ]);
      setIncidents(page.items);
      setStats(summary);
      setError(null);
      setConnected(true);
      setLastUpdated(Date.now());
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) return;
      setConnected(false);
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The incident queue could not be refreshed.",
      );
    } finally {
      setInitialised(true);
    }
  }, [api, search, band, category]);

  const loadResources = useCallback(async () => {
    try {
      const page = await api.resources({ active_only: true, page_size: 100 });
      setResources(page.items);
    } catch {
      // The resource layer is supplementary; the queue reports connection loss.
    }
  }, [api]);

  const loadMap = useCallback(async () => {
    const bounds = viewportRef.current;
    if (!bounds) return;
    try {
      const collection = await api.incidentsInViewport({
        ...bounds,
        openOnly: true,
      });
      setFeatures(collection.features);
    } catch {
      // A stale map is tolerable; the queue is the authoritative view and it
      // surfaces its own errors.
    }
  }, [api]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }

    // The session token lives in browser storage, so this data cannot be
    // fetched in a server component — it has to be loaded on mount. The rule
    // guards against cascading synchronous renders; every setState here
    // happens after an awaited response, which is not that case.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadQueue();
    void loadMap();
    void loadResources();
    const timer = setInterval(() => {
      void loadQueue();
      void loadMap();
      void loadResources();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [authLoading, user, router, loadQueue, loadMap, loadResources]);

  const handleViewportChange = useCallback(
    (bounds: Viewport) => {
      viewportRef.current = bounds;
      void loadMap();
    },
    [loadMap],
  );

  const detail = useSelectedIncident(selectedId);

  const globeMarkers = useMemo(
    () =>
      incidents.map((incident) => ({
        id: incident.id,
        lat: Number(incident.latitude),
        lon: Number(incident.longitude),
        band: incident.priority_band,
        label: `${categoryLabel(incident.category)} ${incident.reference_code}`,
      })),
    [incidents],
  );

  if (authLoading || !initialised) return <Spinner label="Loading the control centre" />;
  if (!user) return null;

  return (
    <div className="space-y-4">
      <CommandStrip connected={connected} lastUpdated={lastUpdated} />
      <StatsBar stats={stats} />
      <ErrorBanner message={error} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="space-y-3">
          <MapControls
            view={view}
            onView={setView}
            showResources={showResources}
            onShowResources={setShowResources}
            resourceCount={resources.length}
          />

          <section
            aria-label={view === "map" ? "Live incident map" : "Globe overview"}
            className="panel-3d relative h-[26rem] overflow-hidden rounded-xl xl:h-[calc(100vh-24rem)] xl:min-h-[26rem]"
          >
            {view === "map" ? (
              <>
                <IncidentMap
                  features={features}
                  resources={resources}
                  showResources={showResources}
                  selectedId={selectedId}
                  onViewportChange={handleViewportChange}
                  onSelect={setSelectedId}
                />
                <div className="pointer-events-none absolute bottom-3 left-3 z-[500]">
                  <MapLegend showResources={showResources} />
                </div>
              </>
            ) : (
              <>
                <GlobeStage
                  label="Globe overview of open incidents"
                  markers={globeMarkers}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  focusLon={MAP_FOCUS_LON}
                />
                <p className="muted absolute left-3 top-3 max-w-xs text-xs">
                  Decorative overview of the {globeMarkers.length} open incidents in the queue.
                  Use the operational map for locations.
                </p>
              </>
            )}
          </section>

          <ActivityTimeline
            entries={detail.history}
            loading={detail.loading}
            error={detail.error}
          />
        </div>

        <div className="space-y-3">
          {selectedId && <SelectedIncident id={selectedId} detail={detail} />}

          <Reveal
            as="section"
            className="panel-3d flex max-h-[40rem] flex-col overflow-hidden rounded-xl xl:max-h-[calc(100vh-14rem)]"
          >
            <div className="space-y-2 border-b border-[var(--border)] p-3">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">Open incidents</h2>
                <span className="muted text-xs">{incidents.length} shown</span>
              </div>

              <TextInput
                type="search"
                placeholder="Search description or reference"
                aria-label="Search incidents"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />

              <div className="grid grid-cols-2 gap-2">
                <select
                  aria-label="Filter by priority"
                  className="surface rounded-lg px-2 py-1.5 text-sm"
                  value={band}
                  onChange={(event) => setBand(event.target.value as PriorityBand | "")}
                >
                  <option value="">All priorities</option>
                  {BANDS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>

                <select
                  aria-label="Filter by category"
                  className="surface rounded-lg px-2 py-1.5 text-sm"
                  value={category}
                  onChange={(event) =>
                    setCategory(event.target.value as IncidentCategory | "")
                  }
                >
                  <option value="">All categories</option>
                  {INCIDENT_CATEGORIES.map((value) => (
                    <option key={value} value={value}>
                      {categoryLabel(value)}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              <IncidentQueue
                incidents={incidents}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </div>
          </Reveal>
        </div>
      </div>
    </div>
  );
}
