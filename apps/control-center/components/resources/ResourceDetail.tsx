"use client";

import { useState } from "react";

import {
  ApiError,
  formatDateTime,
  resourceStatusLabel,
  resourceTypeLabel,
  type Resource,
  type ResourceStatus,
} from "@raksha/api-client";

import { Button, ErrorBanner } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import { changesFrom, formFromResource } from "@/lib/resourceForm";

import { ResourceForm } from "./ResourceForm";
import { ResourceStatusTag } from "./ResourceStatusTag";

/** Statuses a dispatcher may set by hand. The rest follow a dispatch. */
const MANUAL_STATUSES: ResourceStatus[] = ["AVAILABLE", "OUT_OF_SERVICE"];
const COMMITTED: ResourceStatus[] = ["DISPATCHED", "EN_ROUTE", "ON_SCENE"];

export function ResourceDetail({
  resource,
  canManage,
  onChanged,
}: {
  resource: Resource;
  canManage: boolean;
  onChanged: (resource: Resource) => void;
}) {
  const api = getApiClient();
  const [editing, setEditing] = useState(false);
  const [confirmingDeactivate, setConfirmingDeactivate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const committed = COMMITTED.includes(resource.status);

  async function run(action: () => Promise<Resource>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      onChanged(await action());
      setConfirmingDeactivate(false);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Resource detail" className="panel-3d space-y-4 rounded-xl p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">{resource.call_sign}</h2>
          <p className="muted text-sm">{resource.name}</p>
        </div>
        <ResourceStatusTag status={resource.status} />
      </div>

      <ErrorBanner message={error} />

      {editing ? (
        <ResourceForm
          mode="edit"
          initial={formFromResource(resource)}
          onCancel={() => setEditing(false)}
          onSubmit={async (input) => {
            const changes = changesFrom(resource, input);
            if (Object.keys(changes).length === 0) {
              setEditing(false);
              return null;
            }
            try {
              onChanged(await api.updateResource(resource.id, changes));
              setEditing(false);
              return null;
            } catch (caught) {
              return caught instanceof ApiError ? caught.message : "The changes could not be saved.";
            }
          }}
        />
      ) : (
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="muted">Type</dt>
            <dd className="font-medium">{resourceTypeLabel(resource.resource_type)}</dd>
          </div>
          <div>
            <dt className="muted">Crew</dt>
            <dd className="font-medium">{resource.crew_size ?? "—"}</dd>
          </div>
          <div className="col-span-2">
            <dt className="muted">Position</dt>
            <dd className="font-mono">
              {Number(resource.latitude).toFixed(5)}, {Number(resource.longitude).toFixed(5)}
            </dd>
            {resource.base_address && <dd>{resource.base_address}</dd>}
          </div>
          <div className="col-span-2">
            <dt className="muted">Capabilities</dt>
            <dd>{resource.capabilities.length > 0 ? resource.capabilities.join(", ") : "None recorded"}</dd>
          </div>
          <div>
            <dt className="muted">Contact</dt>
            <dd className="font-medium">{resource.contact_phone ?? "—"}</dd>
          </div>
          <div>
            <dt className="muted">Operator</dt>
            <dd className="font-medium">{resource.operator?.full_name ?? "None linked"}</dd>
          </div>
          <div className="col-span-2">
            <dt className="muted">Status last changed</dt>
            <dd>{resource.status_changed_at ? formatDateTime(resource.status_changed_at) : "—"}</dd>
          </div>
          <div className="col-span-2">
            <dt className="muted">Registration</dt>
            <dd>{resource.is_active ? "Active" : "Deactivated — never suggested for dispatch"}</dd>
          </div>
        </dl>
      )}

      {canManage && !editing && (
        <>
          <div className="space-y-2 border-t border-[var(--border)] pt-3">
            <h3 className="text-sm font-semibold">Availability</h3>
            {committed ? (
              <p className="muted text-xs">
                This unit is committed to an incident. Its status follows the dispatch — stand the
                dispatch down from the incident, or the crew reports progress in the responder
                app.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {MANUAL_STATUSES.map((status) => (
                  <Button
                    key={status}
                    variant="secondary"
                    disabled={busy || resource.status === status || !resource.is_active}
                    onClick={() =>
                      void run(
                        () => api.setResourceStatus(resource.id, status),
                        "The status could not be changed.",
                      )
                    }
                  >
                    Set {resourceStatusLabel(status).toLowerCase()}
                  </Button>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2 border-t border-[var(--border)] pt-3">
            <Button variant="secondary" disabled={busy} onClick={() => setEditing(true)}>
              Edit details
            </Button>
            {resource.is_active ? (
              confirmingDeactivate ? (
                <>
                  <Button
                    variant="danger"
                    loading={busy}
                    onClick={() =>
                      void run(
                        () => api.updateResource(resource.id, { is_active: false }),
                        "The unit could not be deactivated.",
                      )
                    }
                  >
                    Confirm deactivate
                  </Button>
                  <Button variant="secondary" onClick={() => setConfirmingDeactivate(false)}>
                    Keep active
                  </Button>
                </>
              ) : (
                <Button
                  variant="danger"
                  disabled={busy || committed}
                  onClick={() => setConfirmingDeactivate(true)}
                >
                  Deactivate…
                </Button>
              )
            ) : (
              <Button
                disabled={busy}
                onClick={() =>
                  void run(
                    () => api.updateResource(resource.id, { is_active: true }),
                    "The unit could not be reactivated.",
                  )
                }
              >
                Reactivate
              </Button>
            )}
          </div>
        </>
      )}

      {!canManage && (
        <p className="muted text-xs">
          Your role can view the inventory but not change it. Dispatchers and administrators
          manage units.
        </p>
      )}
    </section>
  );
}
