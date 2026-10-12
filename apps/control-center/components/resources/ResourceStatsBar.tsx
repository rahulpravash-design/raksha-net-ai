import {
  RESOURCE_TYPES,
  resourceStatusLabel,
  resourceTypeLabel,
  type ResourceStats,
  type ResourceStatus,
} from "@raksha/api-client";

const STATUSES: ResourceStatus[] = ["AVAILABLE", "DISPATCHED", "EN_ROUTE", "ON_SCENE", "OUT_OF_SERVICE"];

/** Counts come straight from the API's summary; nothing is derived client-side. */
export function ResourceStatsBar({ stats }: { stats: ResourceStats | null }) {
  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div className="panel-3d rounded-xl px-4 py-3">
          <dt className="muted text-xs font-medium uppercase tracking-wide">Active units</dt>
          <dd className="mt-1 text-2xl font-bold tabular-nums">{stats?.total_active ?? "—"}</dd>
        </div>
        {STATUSES.map((status) => (
          <div key={status} className="panel-3d rounded-xl px-4 py-3">
            <dt className="muted text-xs font-medium uppercase tracking-wide">
              {resourceStatusLabel(status)}
            </dt>
            <dd className="mt-1 text-2xl font-bold tabular-nums">{stats?.by_status[status] ?? 0}</dd>
          </div>
        ))}
      </dl>
      {stats && (
        <p className="muted text-xs">
          By type:{" "}
          {RESOURCE_TYPES.filter((type) => (stats.by_type[type] ?? 0) > 0)
            .map((type) => `${resourceTypeLabel(type)} ${stats.by_type[type]}`)
            .join(" · ") || "none registered"}
        </p>
      )}
    </div>
  );
}
