"use client";

import { useEffect, useState } from "react";

import {
  confidenceTier,
  formatConfidence,
  formatDateTime,
  type VoiceTranscript,
} from "@raksha/api-client";

import { getApiClient } from "@/lib/api";

/**
 * Says that a report was dictated, and what the speech model heard.
 *
 * The incident's description is the reporter's confirmed text and is shown as such
 * elsewhere. This panel is the AI-derived record behind it (CLAUDE.md section 2,
 * rules 2 and 3): the model, its confidence, and whether the reporter changed the words.
 * The model's own words are shown only when they differ from the description, since
 * otherwise they are the description.
 *
 * It renders nothing for a typed report. If the record cannot be loaded it says so
 * rather than silently implying the report was typed.
 */
export function VoiceTranscriptPanel({ incidentId }: { incidentId: string }) {
  const [rows, setRows] = useState<VoiceTranscript[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const loaded = await getApiClient().listTranscripts(incidentId);
        if (!cancelled) setRows(loaded);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    // The session token lives in browser storage, so this cannot be fetched
    // server-side; every setState here follows an awaited response.
    void load();
    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  if (failed) {
    return (
      <p className="muted text-xs">
        Whether this report was dictated could not be checked just now.
      </p>
    );
  }
  if (!rows || rows.length === 0) return null;

  return (
    <section className="surface space-y-3 rounded-xl p-4" aria-label="Dictated report">
      <h2 className="font-semibold">Dictated report</h2>
      <p className="muted text-xs">
        The reporter spoke this report and read the text before sending it. What the speech
        model heard is AI-derived and unverified.
      </p>
      <ul className="space-y-3">
        {rows.map((row) => (
          <li key={row.id} className="rounded-lg border border-[var(--border)] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-900 dark:bg-violet-900 dark:text-violet-100">
                AI transcript
              </span>
              <span className="muted text-xs">
                {row.model_name} v{row.model_version} · {formatDateTime(row.created_at)}
              </span>
            </div>
            <p className="mt-2 text-sm">
              {row.reporter_edited
                ? "The reporter corrected the transcript before sending."
                : "Sent as transcribed."}{" "}
              <span
                className={
                  confidenceTier(row.confidence) === "low" ? "muted italic" : "muted"
                }
              >
                Recogniser: {formatConfidence(row.confidence)}
                {row.language ? `, heard as ${row.language}` : ""}.
              </span>
            </p>
            {row.reporter_edited && (
              <details className="mt-2 text-sm">
                <summary className="cursor-pointer">What the speech model heard</summary>
                <blockquote className="muted mt-1 border-l-2 border-[var(--border)] pl-3">
                  {row.text}
                </blockquote>
              </details>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
