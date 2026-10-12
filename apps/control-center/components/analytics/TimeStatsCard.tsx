import type { TimeStats } from "@raksha/api-client";

import { formatMinutes, isSmallSample } from "@/lib/analytics";

/**
 * One time measure. The sample size is always on the card; with no cases the
 * card says so plainly rather than showing zero (which would read as "instant").
 */
export function TimeStatsCard({
  title,
  description,
  stats,
}: {
  title: string;
  description: string;
  stats: TimeStats | null;
}) {
  return (
    <section aria-label={title} className="panel-3d rounded-xl p-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="muted text-xs">{description}</p>

      {stats === null && <p className="muted mt-3 text-sm">Loading…</p>}

      {stats !== null && stats.sample_size === 0 && (
        <p className="mt-3 text-sm">
          No incidents in this period have reached this point yet, so there is nothing to
          measure.
        </p>
      )}

      {stats !== null && stats.sample_size > 0 && (
        <>
          <p className="mt-3 text-3xl font-bold tabular-nums">{formatMinutes(stats.median_minutes)}</p>
          <p className="muted text-xs">median, from {stats.sample_size} incident{stats.sample_size === 1 ? "" : "s"}</p>
          {isSmallSample(stats.sample_size) && (
            <p role="note" className="mt-2 text-xs text-amber-300">
              Based on very few cases — treat it as an anecdote, not a trend.
            </p>
          )}
          <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
            <div>
              <dt className="muted text-xs">Fastest</dt>
              <dd className="font-medium">{formatMinutes(stats.min_minutes)}</dd>
            </div>
            <div>
              <dt className="muted text-xs">Average</dt>
              <dd className="font-medium">{formatMinutes(stats.avg_minutes)}</dd>
            </div>
            <div>
              <dt className="muted text-xs">Slowest</dt>
              <dd className="font-medium">{formatMinutes(stats.max_minutes)}</dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}
