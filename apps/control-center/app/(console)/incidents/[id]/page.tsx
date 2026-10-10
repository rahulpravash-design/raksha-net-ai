"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  OPEN_STATUSES,
  canDispatch,
  type Incident,
  type StatusHistoryEntry,
} from "@raksha/api-client";

import { Reveal } from "@/components/animations/Reveal";
import { AIAnalysisPanel } from "@/components/AIAnalysisPanel";
import { useAuth } from "@/components/AuthProvider";
import { DispatchPanel } from "@/components/DispatchPanel";
import { Collapsible } from "@/components/incident/Collapsible";
import { IncidentActions } from "@/components/incident/IncidentActions";
import { IncidentHeader } from "@/components/incident/IncidentHeader";
import { IncidentSkeleton } from "@/components/incident/IncidentSkeleton";
import { LocationBody, SituationBody } from "@/components/incident/SituationPanel";
import { StatusTimeline } from "@/components/incident/StatusTimeline";
import { MediaGallery } from "@/components/MediaGallery";
import { PriorityExplanation } from "@/components/PriorityExplanation";
import { Button, ErrorBanner } from "@/components/ui";
import { getApiClient } from "@/lib/api";

export default function IncidentConsolePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [incident, setIncident] = useState<Incident | null>(null);
  const [history, setHistory] = useState<StatusHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [detail, entries] = await Promise.all([
        api.incident(params.id),
        api.incidentHistory(params.id),
      ]);
      setIncident(detail);
      setHistory(entries);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "The incident could not be loaded.",
      );
    }
  }, [api, params.id]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // The session token lives in browser storage, so this data cannot be
    // fetched in a server component — it has to be loaded on mount. Every
    // setState here follows an awaited response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [authLoading, user, router, load]);

  if (!incident) {
    if (error) {
      return (
        <div className="space-y-3">
          <ErrorBanner message={error} />
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => void load()}>
              Try again
            </Button>
            <Link href="/dashboard" className="surface rounded-lg px-4 py-2.5 text-sm font-semibold">
              Back to the queue
            </Link>
          </div>
        </div>
      );
    }
    return <IncidentSkeleton />;
  }

  const mayDispatch = user ? canDispatch(user.role) : false;

  return (
    <div className="space-y-4">
      <Link href="/dashboard" className="muted text-sm hover:underline">
        ← Back to the queue
      </Link>

      <ErrorBanner message={error} />
      <Reveal>
        <IncidentHeader incident={incident} />
      </Reveal>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Reveal index={1}>
            <Collapsible title="Reported situation">
              <SituationBody incident={incident} />
            </Collapsible>
          </Reveal>

          <Reveal index={2}>
            <AIAnalysisPanel
              incidentId={incident.id}
              canReview={mayDispatch}
              onApplied={() => void load()}
            />
          </Reveal>

          <Reveal index={3}>
            <Collapsible title="Location">
              <LocationBody incident={incident} />
            </Collapsible>
          </Reveal>

          <Reveal index={4}>
            <Collapsible
              title="Photographs"
              summary={`${incident.media.length} attached`}
              defaultOpen={incident.media.length > 0}
            >
              <MediaGallery media={incident.media} />
            </Collapsible>
          </Reveal>

          <Reveal index={5}>
            <Collapsible title="Audit trail" summary={`${history.length} entries`}>
              <StatusTimeline entries={history} />
            </Collapsible>
          </Reveal>
        </div>

        <aside className="space-y-4">
          <Reveal index={2}>
            <PriorityExplanation incident={incident} />
          </Reveal>

          <DispatchPanel
            incidentId={incident.id}
            incidentOpen={OPEN_STATUSES.includes(incident.status)}
            canDispatch={mayDispatch}
            onChanged={() => void load()}
          />

          {mayDispatch ? (
            <IncidentActions incident={incident} onChanged={load} />
          ) : (
            <section className="panel-3d rounded-xl p-4">
              <p className="muted text-sm">
                Your role can view this incident but not change it. Dispatch actions are
                limited to dispatchers and administrators.
              </p>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
