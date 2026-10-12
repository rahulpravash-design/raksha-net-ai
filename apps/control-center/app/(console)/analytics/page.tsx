"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  INCIDENT_CATEGORIES,
  canDispatch,
  categoryLabel,
  resourceTypeLabel,
  type CategoryBreakdown,
  type Hotspots,
  type IncidentCategory,
  type ResourceUtilization,
  type TimeStats,
} from "@raksha/api-client";

import { BarList, type BarRow } from "@/components/analytics/BarList";
import { TimeStatsCard } from "@/components/analytics/TimeStatsCard";
import { useAuth } from "@/components/AuthProvider";
import { EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import { PERIODS, cellSizeKm, sinceFor, type PeriodKey } from "@/lib/analytics";
import { homeFor } from "@/lib/routes";

interface Data {
  response: TimeStats;
  resolution: TimeStats;
  categories: CategoryBreakdown;
  utilization: ResourceUtilization;
  hotspots: Hotspots;
}

export default function AnalyticsPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();
  const [period, setPeriod] = useState<PeriodKey>("7d");
  const [category, setCategory] = useState<IncidentCategory | "">("");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const since = sinceFor(period);
    const range = since ? { since } : {};
    const scoped = { ...range, ...(category ? { category } : {}) };
    try {
      const [response, resolution, categories, utilization, hotspots] = await Promise.all([
        api.responseTime(scoped),
        api.resolutionTime(scoped),
        api.categoryBreakdown(range),
        api.resourceUtilization(range),
        api.hotspots({ ...scoped, limit: 15 }),
      ]);
      setData({ response, resolution, categories, utilization, hotspots });
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) return;
      setError(caught instanceof ApiError ? caught.message : "Analytics could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [api, period, category]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (!canDispatch(user.role)) {
      router.replace(homeFor(user.role));
      return;
    }
    // Session token is in browser storage; every setState follows an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [authLoading, user, router, load]);

  const categoryRows = useMemo<BarRow[]>(
    () =>
      (data?.categories.items ?? []).map((item) => ({
        key: item.category,
        label: categoryLabel(item.category),
        value: item.count,
        valueLabel: String(item.count),
        detail:
          item.avg_priority_score === null
            ? "No priority scores yet"
            : `average priority score ${item.avg_priority_score.toFixed(0)}`,
      })),
    [data],
  );

  const utilizationRows = useMemo<BarRow[]>(
    () =>
      (data?.utilization.items ?? []).map((item) => ({
        key: item.resource_type,
        label: resourceTypeLabel(item.resource_type),
        value: item.dispatches_in_period,
        valueLabel: `${item.dispatches_in_period} dispatch${item.dispatches_in_period === 1 ? "" : "es"}`,
        detail: `${item.available_now} of ${item.total_resources} available now · ${item.avg_dispatches_per_resource.toFixed(1)} per unit`,
      })),
    [data],
  );

  const hotspotRows = useMemo<BarRow[]>(
    () =>
      (data?.hotspots.items ?? []).map((cell, index) => ({
        key: `${cell.latitude},${cell.longitude}`,
        label: `Area ${index + 1} · near ${cell.latitude.toFixed(2)}, ${cell.longitude.toFixed(2)}`,
        value: cell.incident_count,
        valueLabel: `${cell.incident_count} incident${cell.incident_count === 1 ? "" : "s"}`,
      })),
    [data],
  );

  if (authLoading || !user || !canDispatch(user.role)) return <Spinner label="Loading analytics" />;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold tracking-wide">ANALYTICS</h1>
        <p className="muted text-xs">
          How the response is performing. These are operational measures, not a forecast: nothing
          here predicts future incidents.
        </p>
      </div>

      <div className="panel-3d flex flex-wrap items-center gap-3 rounded-xl p-3">
        <div role="group" aria-label="Period" className="flex flex-wrap gap-1">
          {PERIODS.map((option) => (
            <button
              key={option.key}
              type="button"
              aria-pressed={period === option.key}
              onClick={() => setPeriod(option.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                period === option.key ? "bg-[var(--accent)] text-[#050914]" : "hover:bg-white/10"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="muted text-xs">Category (times and hotspots)</span>
          <select
            aria-label="Filter by category"
            className="surface rounded-lg px-2 py-1.5 text-sm"
            value={category}
            onChange={(e) => setCategory(e.target.value as IncidentCategory | "")}
          >
            <option value="">All categories</option>
            {INCIDENT_CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {categoryLabel(value)}
              </option>
            ))}
          </select>
        </label>
        {loading && <span role="status" className="muted text-xs">Updating…</span>}
      </div>

      <ErrorBanner message={error} />

      {!data && !error && <Spinner label="Loading analytics" />}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <TimeStatsCard
              title="Time to first dispatch"
              description="From the report being filed to the first unit being dispatched."
              stats={data.response}
            />
            <TimeStatsCard
              title="Time to resolution"
              description="From the report being filed to the incident being marked resolved."
              stats={data.resolution}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section aria-label="Incidents by category" className="panel-3d rounded-xl p-4">
              <h2 className="font-semibold">Incidents by category</h2>
              <p className="muted mb-3 text-xs">{data.categories.total} incidents in the period.</p>
              {categoryRows.length === 0 ? (
                <p className="muted text-sm">No incidents in this period.</p>
              ) : (
                <BarList rows={categoryRows} label="Incidents by category" />
              )}
            </section>

            <section aria-label="Resource use" className="panel-3d rounded-xl p-4">
              <h2 className="font-semibold">Resource use</h2>
              <p className="muted mb-3 text-xs">
                Dispatches per unit type in the period; availability is as of now.
              </p>
              {utilizationRows.length === 0 ? (
                <p className="muted text-sm">No resources are registered.</p>
              ) : (
                <BarList rows={utilizationRows} label="Dispatches by resource type" />
              )}
            </section>
          </div>

          <section aria-label="Hotspots" className="panel-3d rounded-xl p-4">
            <h2 className="font-semibold">Where incidents cluster</h2>
            <p className="muted mb-3 text-xs">
              Counts per grid cell about {cellSizeKm(data.hotspots.cell_size_degrees)} km across.
              Positions are cell centres — deliberately never an individual report&apos;s location.
            </p>
            {hotspotRows.length === 0 ? (
              <EmptyState title="No incidents in this period" body="Nothing to cluster yet." />
            ) : (
              <BarList rows={hotspotRows} label="Incident counts by area" />
            )}
          </section>
        </>
      )}
    </div>
  );
}
