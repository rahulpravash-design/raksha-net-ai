"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  INCIDENT_CATEGORIES,
  categoryLabel,
  confidenceTier,
  formatConfidence,
  formatDateTime,
  observationLabel,
  type AnalysisReviewDecision,
  type IncidentAnalysis,
  type IncidentCategory,
  type SeverityLevel,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

const SEVERITIES: SeverityLevel[] = ["CRITICAL", "HIGH", "MODERATE", "LOW"];

const CONFIDENCE_CLASS: Record<string, string> = {
  high: "font-semibold text-[var(--foreground)]",
  medium: "text-[var(--foreground)]",
  low: "muted italic",
};

function ConfidenceTag({ confidence }: { confidence: number | null }) {
  return (
    <span className={`ml-1 text-xs ${CONFIDENCE_CLASS[confidenceTier(confidence)]}`}>
      {formatConfidence(confidence)}
    </span>
  );
}

function triStateLabel(value: boolean | null, whenTrue: string): string {
  if (value === null) return "Not mentioned";
  return value ? whenTrue : "No";
}

interface EditDraft {
  category: IncidentCategory | "";
  severity: SeverityLevel | "";
  peopleAffected: string;
  peopleTrapped: boolean | null;
  medicalRequired: boolean | null;
  immediateDanger: boolean | null;
}

function draftFrom(analysis: IncidentAnalysis): EditDraft {
  return {
    category: analysis.proposed_category ?? "",
    severity: analysis.proposed_severity ?? "",
    peopleAffected: analysis.people_affected?.toString() ?? "",
    peopleTrapped: analysis.people_trapped,
    medicalRequired: analysis.medical_support_required,
    immediateDanger: analysis.immediate_rescue_required,
  };
}

/**
 * The dispatcher review surface for an AI proposal.
 *
 * CLAUDE.md section 2, rule 1: AI proposes, a human disposes. Nothing here
 * writes to the incident directly — every button calls the review endpoint,
 * which is the only thing that can turn a proposal into a fact, and only for
 * a dispatcher (`canReview`).
 */
export function AIAnalysisPanel({
  incidentId,
  canReview,
  onApplied,
}: {
  incidentId: string;
  canReview: boolean;
  /** Called after a review changes the incident, so the parent can reload it. */
  onApplied: () => void;
}) {
  const api = getApiClient();
  const [analyses, setAnalyses] = useState<IncidentAnalysis[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const rows = await api.listAnalyses(incidentId);
      setAnalyses(rows);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "AI analyses could not be loaded.",
      );
    }
  }, [api, incidentId]);

  useEffect(() => {
    // The session token lives in browser storage, so this cannot be fetched
    // server-side; every setState here follows an awaited response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function runAnalysis() {
    setBusy(true);
    setError(null);
    try {
      await api.runAnalysis(incidentId);
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The analysis could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function submitReview(analysisId: string, decision: AnalysisReviewDecision) {
    setBusy(true);
    setError(null);
    try {
      if (decision === "EDITED" && draft) {
        await api.reviewAnalysis(incidentId, analysisId, {
          decision,
          note: notes[analysisId]?.trim() || null,
          category: draft.category || null,
          severity: draft.severity || null,
          people_affected: draft.peopleAffected ? Number(draft.peopleAffected) : null,
          people_trapped: draft.peopleTrapped,
          medical_required: draft.medicalRequired,
          immediate_danger: draft.immediateDanger,
        });
      } else {
        await api.reviewAnalysis(incidentId, analysisId, {
          decision,
          note: notes[analysisId]?.trim() || null,
        });
      }
      setEditingId(null);
      setDraft(null);
      await load();
      onApplied();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The review could not be recorded.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="surface space-y-3 rounded-xl p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">AI analysis</h2>
        <Button variant="secondary" disabled={busy} onClick={() => void runAnalysis()}>
          Run AI analysis
        </Button>
      </div>
      <p className="muted text-xs">
        A proposal drawn from the reporter&apos;s own words. It never changes
        the incident until a dispatcher accepts, edits or rejects it below.
      </p>

      <ErrorBanner message={error} />

      {analyses !== null && analyses.length === 0 && (
        <p className="muted text-sm">No AI analysis has been requested yet.</p>
      )}

      {analyses !== null && analyses.length > 0 && (
        <ul className="space-y-3">
          {analyses.map((analysis) => (
            <li
              key={analysis.id}
              className="rounded-lg border border-[var(--border)] p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-900 dark:bg-violet-900 dark:text-violet-100">
                  AI proposal
                </span>
                <span className="muted text-xs">
                  {analysis.model_name} v{analysis.model_version} ·{" "}
                  {formatDateTime(analysis.created_at)}
                </span>
              </div>

              <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                <div>
                  <dt className="muted">Category</dt>
                  <dd>
                    {analysis.proposed_category
                      ? categoryLabel(analysis.proposed_category)
                      : "Not determined"}
                    {analysis.proposed_category && (
                      <ConfidenceTag confidence={analysis.type_confidence} />
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="muted">Severity</dt>
                  <dd>
                    {analysis.proposed_severity ?? "Not determined"}
                    {analysis.proposed_severity && (
                      <ConfidenceTag confidence={analysis.severity_confidence} />
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="muted">People affected</dt>
                  <dd>{analysis.people_affected ?? "Not mentioned"}</dd>
                </div>
                <div>
                  <dt className="muted">Trapped</dt>
                  <dd>{triStateLabel(analysis.people_trapped, "Yes")}</dd>
                </div>
                <div>
                  <dt className="muted">Medical support</dt>
                  <dd>{triStateLabel(analysis.medical_support_required, "Suggested")}</dd>
                </div>
                <div>
                  <dt className="muted">Immediate rescue</dt>
                  <dd>{triStateLabel(analysis.immediate_rescue_required, "Suggested")}</dd>
                </div>
              </dl>

              {analysis.observations.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs font-semibold">
                    Observations{" "}
                    <span className="muted font-normal">
                      (AI observations, not verified facts)
                    </span>
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-1.5" aria-label="AI observations">
                    {analysis.observations.map((observation) => (
                      <li
                        key={`${observation.source}-${observation.label}`}
                        title="AI observation: unverified"
                        className="inline-flex items-center rounded-full border border-dashed border-violet-400 px-2 py-0.5 text-xs"
                      >
                        <span className="mr-1 font-semibold text-violet-700 dark:text-violet-300">
                          AI ·
                        </span>
                        {observationLabel(observation.label)}
                        {observation.source === "IMAGE" && (
                          <span className="muted ml-1">(photo)</span>
                        )}
                        <ConfidenceTag confidence={observation.confidence} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {analysis.reasoning_factors.length > 0 && (
                <ul className="muted mt-2 list-inside list-disc text-xs">
                  {analysis.reasoning_factors.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}

              {analysis.review_decision ? (
                <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800">
                  <p className="font-medium">
                    {analysis.review_decision === "ACCEPTED" && "Accepted"}
                    {analysis.review_decision === "EDITED" && "Accepted with edits"}
                    {analysis.review_decision === "REJECTED" && "Rejected"}
                    {analysis.reviewed_by ? ` by ${analysis.reviewed_by.full_name}` : ""}
                  </p>
                  {analysis.review_note && (
                    <p className="muted mt-1 text-xs">{analysis.review_note}</p>
                  )}
                </div>
              ) : !canReview ? (
                <p className="muted mt-3 text-xs">Awaiting a dispatcher&apos;s review.</p>
              ) : editingId === analysis.id && draft ? (
                <div className="mt-3 space-y-2 rounded-lg border border-[var(--border)] p-3">
                  <Field label="Category">
                    <select
                      aria-label="Corrected category"
                      className="surface w-full rounded-lg px-3 py-2 text-sm"
                      value={draft.category}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          category: event.target.value as IncidentCategory | "",
                        })
                      }
                    >
                      <option value="">No change</option>
                      {INCIDENT_CATEGORIES.map((value) => (
                        <option key={value} value={value}>
                          {categoryLabel(value)}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Severity">
                    <select
                      aria-label="Corrected severity"
                      className="surface w-full rounded-lg px-3 py-2 text-sm"
                      value={draft.severity}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          severity: event.target.value as SeverityLevel | "",
                        })
                      }
                    >
                      <option value="">No change</option>
                      {SEVERITIES.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="People affected">
                    <TextInput
                      type="number"
                      min={0}
                      value={draft.peopleAffected}
                      onChange={(event) =>
                        setDraft({ ...draft, peopleAffected: event.target.value })
                      }
                    />
                  </Field>
                  <Field label="Note" hint="Recorded with the review.">
                    <TextInput
                      value={notes[analysis.id] ?? ""}
                      onChange={(event) =>
                        setNotes({ ...notes, [analysis.id]: event.target.value })
                      }
                      placeholder="Why you changed it"
                    />
                  </Field>
                  <div className="flex gap-2">
                    <Button
                      disabled={busy}
                      onClick={() => void submitReview(analysis.id, "EDITED")}
                    >
                      Save correction
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => {
                        setEditingId(null);
                        setDraft(null);
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    disabled={busy}
                    onClick={() => void submitReview(analysis.id, "ACCEPTED")}
                  >
                    Accept
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => {
                      setEditingId(analysis.id);
                      setDraft(draftFrom(analysis));
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="danger"
                    disabled={busy}
                    onClick={() => void submitReview(analysis.id, "REJECTED")}
                  >
                    Reject
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
