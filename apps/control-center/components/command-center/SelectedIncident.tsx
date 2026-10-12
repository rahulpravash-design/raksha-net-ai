"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  categoryLabel,
  formatConfidence,
  formatRelative,
  resourceTypeLabel,
  statusLabel,
  type Incident,
  type IncidentAnalysis,
  type ResourceRecommendation,
  type StatusHistoryEntry,
} from "@raksha/api-client";

import { PriorityBadge } from "@/components/ui";
import { getApiClient } from "@/lib/api";

export interface SelectedDetail {
  incident: Incident | null;
  analysis: IncidentAnalysis | null;
  recommendations: ResourceRecommendation[] | null;
  history: StatusHistoryEntry[] | null;
  loading: boolean;
  error: string | null;
}

const EMPTY: SelectedDetail = {
  incident: null,
  analysis: null,
  recommendations: null,
  history: null,
  loading: false,
  error: null,
};

/**
 * Loads what the command centre shows about one incident, all from the API.
 * A late response for a previously selected incident is discarded.
 */
export function useSelectedIncident(id: string | null): SelectedDetail {
  const [detail, setDetail] = useState<SelectedDetail>(EMPTY);

  useEffect(() => {
    if (!id) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDetail(EMPTY);
      return;
    }
    let cancelled = false;
    const api = getApiClient();
    setDetail({ ...EMPTY, loading: true });
    void (async () => {
      try {
        const [incident, analyses, history, ranked] = await Promise.all([
          api.incident(id),
          api.listAnalyses(id),
          api.incidentHistory(id),
          api.resourceRecommendations(id, 3),
        ]);
        if (cancelled) return;
        setDetail({
          incident,
          analysis: analyses[0] ?? null,
          recommendations: ranked.items,
          history,
          loading: false,
          error: null,
        });
      } catch (caught) {
        if (cancelled) return;
        setDetail({
          ...EMPTY,
          error:
            caught instanceof ApiError
              ? caught.message
              : "The incident details could not be loaded.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  return detail;
}

/**
 * Summary of the selected incident. Human-verified facts, the engine's score
 * and the AI's proposal are kept visibly apart, and nothing here can dispatch:
 * dispatch lives in the incident console, behind an explicit confirmation.
 */
export function SelectedIncident({
  id,
  detail,
  onQuickView,
}: {
  id: string;
  detail: SelectedDetail;
  onQuickView?: () => void;
}) {
  const { incident, analysis, recommendations, loading, error } = detail;

  return (
    <section aria-label="Selected incident" className="panel-3d space-y-3 rounded-xl p-3">
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
      {loading && !incident && <p className="muted text-sm">Loading incident…</p>}

      {incident && (
        <>
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="font-semibold">{categoryLabel(incident.category)}</h2>
              <p className="muted text-xs">
                <span className="font-mono">{incident.reference_code}</span> ·{" "}
                {statusLabel(incident.status)} · {formatRelative(incident.created_at)}
              </p>
            </div>
            <PriorityBadge band={incident.priority_band} />
          </div>

          <p className="line-clamp-3 text-sm">{incident.description}</p>

          {incident.priority_factors && incident.priority_factors.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--accent)]">
                Priority — engine score {incident.priority_score ?? "—"}
              </h3>
              <ul className="mt-1 space-y-0.5 text-xs">
                {incident.priority_factors.slice(0, 4).map((factor) => (
                  <li key={factor.key} className="flex justify-between gap-2">
                    <span>{factor.label}</span>
                    <span className="tabular-nums">
                      {factor.points >= 0 ? "+" : ""}
                      {factor.points}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="rounded-lg border border-violet-400/40 p-2">
            <p className="text-xs font-semibold text-violet-300">
              AI proposal — not verified
            </p>
            {analysis ? (
              <p className="mt-1 text-xs">
                {analysis.proposed_category ? categoryLabel(analysis.proposed_category) : "No category"}
                {analysis.proposed_severity ? `, ${analysis.proposed_severity.toLowerCase()} severity` : ""}{" "}
                ({formatConfidence(analysis.type_confidence)}).{" "}
                {analysis.review_decision
                  ? `Operator review: ${analysis.review_decision.toLowerCase()}.`
                  : "Awaiting operator review."}
                <span className="muted block">
                  {analysis.model_name} v{analysis.model_version}
                </span>
              </p>
            ) : (
              <p className="muted mt-1 text-xs">No AI analysis has been requested.</p>
            )}
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--accent)]">
              Suggested units
            </h3>
            {recommendations && recommendations.length > 0 ? (
              <ul className="mt-1 space-y-0.5 text-xs">
                {recommendations.map((item) => (
                  <li key={item.resource.id}>
                    #{item.rank} {item.resource.call_sign} ·{" "}
                    {resourceTypeLabel(item.resource.resource_type)} ·{" "}
                    {item.resource.distance_km.toFixed(1)} km · about {item.estimated_minutes} min
                    (straight-line estimate)
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted mt-1 text-xs">No available unit found nearby.</p>
            )}
            <p className="muted mt-1 text-xs">Suggestions only — dispatch is a human decision.</p>
          </div>

          <div className="flex gap-2">
            {onQuickView && (
              <button
                type="button"
                onClick={onQuickView}
                className="surface flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold"
              >
                Quick view
              </button>
            )}
            <Link
              href={`/incidents/${id}`}
              className="flex-1 rounded-lg bg-brand-600 px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-brand-700"
            >
              Open incident console
            </Link>
          </div>
        </>
      )}
    </section>
  );
}
