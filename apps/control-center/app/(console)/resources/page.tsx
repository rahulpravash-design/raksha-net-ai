"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  RESOURCE_TYPES,
  canDispatch,
  resourceStatusLabel,
  resourceTypeLabel,
  type Page,
  type Resource,
  type ResourceStats,
  type ResourceStatus,
  type ResourceType,
} from "@raksha/api-client";

import { Reveal } from "@/components/animations/Reveal";
import { useAuth } from "@/components/AuthProvider";
import { ResourceCard } from "@/components/resources/ResourceCard";
import { ResourceDetail } from "@/components/resources/ResourceDetail";
import { ResourceForm } from "@/components/resources/ResourceForm";
import { ResourceStatsBar } from "@/components/resources/ResourceStatsBar";
import { Button, EmptyState, ErrorBanner, Spinner, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import { EMPTY_RESOURCE_FORM } from "@/lib/resourceForm";

const PAGE_SIZE = 24;
const REFRESH_MS = 20_000;
const STATUSES: ResourceStatus[] = ["AVAILABLE", "DISPATCHED", "EN_ROUTE", "ON_SCENE", "OUT_OF_SERVICE"];

export default function ResourcesPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();
  const canManage = user ? canDispatch(user.role) : false;

  const [result, setResult] = useState<Page<Resource> | null>(null);
  const [stats, setStats] = useState<ResourceStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [search, setSearch] = useState("");
  const [type, setType] = useState<ResourceType | "">("");
  const [status, setStatus] = useState<ResourceStatus | "">("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    try {
      const [list, summary] = await Promise.all([
        api.resources({
          page,
          page_size: PAGE_SIZE,
          active_only: !includeInactive,
          ...(search.trim() ? { q: search.trim() } : {}),
          ...(type ? { resource_type: [type] } : {}),
          ...(status ? { status: [status] } : {}),
        }),
        api.resourceStats(),
      ]);
      setResult(list);
      setStats(summary);
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) return;
      setError(caught instanceof ApiError ? caught.message : "The inventory could not be loaded.");
    }
  }, [api, page, search, type, status, includeInactive]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // Session token is in browser storage; every setState follows an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [authLoading, user, router, load]);

  const selected = result?.items.find((item) => item.id === selectedId) ?? null;

  function changeFilter<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  if (authLoading || (!result && !error)) return <Spinner label="Loading the resource inventory" />;
  if (!user) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-wide">RESOURCES</h1>
          <p className="muted text-xs">
            Units that can be suggested for dispatch. Availability changes here are recorded in the
            audit log.
          </p>
        </div>
        {canManage && !creating && (
          <Button onClick={() => setCreating(true)}>Register a resource</Button>
        )}
      </div>

      <ErrorBanner message={error} />
      <ResourceStatsBar stats={stats} />

      {creating && (
        <Reveal as="section" className="panel-3d rounded-xl p-4">
          <h2 className="mb-3 font-semibold">Register a resource</h2>
          <ResourceForm
            mode="create"
            initial={EMPTY_RESOURCE_FORM}
            onCancel={() => setCreating(false)}
            onSubmit={async (input) => {
              try {
                const created = await api.createResource(input);
                setCreating(false);
                setSelectedId(created.id);
                await load();
                return null;
              } catch (caught) {
                return caught instanceof ApiError
                  ? caught.message
                  : "The resource could not be registered.";
              }
            }}
          />
        </Reveal>
      )}

      <div className="panel-3d grid gap-2 rounded-xl p-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_auto]">
        <TextInput
          type="search"
          aria-label="Search resources"
          placeholder="Search call sign or name"
          value={search}
          onChange={(e) => changeFilter(setSearch)(e.target.value)}
        />
        <select
          aria-label="Filter by type"
          className="surface rounded-lg px-2 py-2 text-sm"
          value={type}
          onChange={(e) => changeFilter(setType)(e.target.value as ResourceType | "")}
        >
          <option value="">All types</option>
          {RESOURCE_TYPES.map((value) => (
            <option key={value} value={value}>
              {resourceTypeLabel(value)}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by status"
          className="surface rounded-lg px-2 py-2 text-sm"
          value={status}
          onChange={(e) => changeFilter(setStatus)(e.target.value as ResourceStatus | "")}
        >
          <option value="">All statuses</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {resourceStatusLabel(value)}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 px-2 text-sm">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => changeFilter(setIncludeInactive)(e.target.checked)}
          />
          Show deactivated
        </label>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="space-y-3">
          {result && result.items.length === 0 ? (
            <EmptyState
              title="No resources match"
              body={
                stats?.total_active === 0
                  ? "No units are registered yet. A dispatcher or administrator can register one."
                  : "Try clearing a filter."
              }
            />
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3" aria-label="Resources">
              {result?.items.map((resource, index) => (
                <ResourceCard
                  key={resource.id}
                  resource={resource}
                  index={index}
                  selected={resource.id === selectedId}
                  onSelect={() => setSelectedId(resource.id)}
                />
              ))}
            </ul>
          )}

          {result && result.pages > 1 && (
            <nav aria-label="Pagination" className="flex items-center justify-between text-sm">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <span className="muted">
                Page {result.page} of {result.pages} · {result.total} units
              </span>
              <Button
                variant="secondary"
                disabled={page >= result.pages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </nav>
          )}
        </div>

        <div>
          {selected ? (
            <ResourceDetail
              key={selected.id}
              resource={selected}
              canManage={canManage}
              onChanged={() => void load()}
            />
          ) : (
            <p className="panel-3d muted rounded-xl p-4 text-sm">
              Select a unit to see its details{canManage ? " and manage it" : ""}.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
