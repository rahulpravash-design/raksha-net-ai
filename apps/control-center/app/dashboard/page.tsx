"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  INCIDENT_CATEGORIES,
  categoryLabel,
  type GeoFeature,
  type IncidentCategory,
  type IncidentStats,
  type IncidentSummary,
  type PriorityBand,
} from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import { IncidentQueue } from "@/components/IncidentQueue";
import { StatsBar } from "@/components/StatsBar";
import { ErrorBanner, Spinner, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
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

const BANDS: PriorityBand[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function DashboardPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [stats, setStats] = useState<IncidentStats | null>(null);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [features, setFeatures] = useState<GeoFeature[]>([]);
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
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) return;
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The incident queue could not be refreshed.",
      );
    } finally {
      setInitialised(true);
    }
  }, [api, search, band, category]);

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
    const timer = setInterval(() => {
      void loadQueue();
      void loadMap();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [authLoading, user, router, loadQueue, loadMap]);

  const handleViewportChange = useCallback(
    (bounds: Viewport) => {
      viewportRef.current = bounds;
      void loadMap();
    },
    [loadMap],
  );

  if (authLoading || !initialised) return <Spinner label="Loading the control centre" />;
  if (!user) return null;

  return (
    <div className="space-y-4">
      <StatsBar stats={stats} />
      <ErrorBanner message={error} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_26rem]">
        <section
          aria-label="Live incident map"
          className="h-[28rem] lg:h-[calc(100vh-16rem)]"
        >
          <IncidentMap
            features={features}
            selectedId={selectedId}
            onViewportChange={handleViewportChange}
            onSelect={setSelectedId}
          />
        </section>

        <section
          aria-label="Incident queue"
          className="surface flex max-h-[calc(100vh-16rem)] flex-col overflow-hidden rounded-xl"
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
                onChange={(event) =>
                  setBand(event.target.value as PriorityBand | "")
                }
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

          {selectedId && (
            <div className="border-t border-[var(--border)] p-3">
              <Link
                href={`/incidents/${selectedId}`}
                className="block rounded-lg bg-brand-600 px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-brand-700"
              >
                Open incident
              </Link>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
