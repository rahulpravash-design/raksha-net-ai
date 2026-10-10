"use client";

import { useEffect, useState } from "react";

/** Seconds since `at`, re-evaluated every few seconds while mounted. */
export function useAgeSeconds(at: number | null): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5_000);
    return () => window.clearInterval(timer);
  }, []);
  return at === null ? null : Math.max(0, Math.round((now - at) / 1000));
}

export function describeAge(seconds: number): string {
  if (seconds < 10) return "just now";
  if (seconds < 90) return `${seconds} s ago`;
  return `${Math.round(seconds / 60)} min ago`;
}

/**
 * Connection state and data freshness, both derived from the real polling
 * results — nothing here is decorative. A lost connection says so, and says how
 * old the data on screen is.
 */
export function CommandStrip({
  connected,
  lastUpdated,
}: {
  connected: boolean;
  lastUpdated: number | null;
}) {
  const age = useAgeSeconds(lastUpdated);
  const stale = age !== null && age > 45;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-lg font-bold tracking-wide">COMMAND CENTRE</h1>
        <p className="muted text-xs">
          Open incidents, ranked by the deterministic priority engine.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs" role="status">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-semibold ${
            connected
              ? "border-[var(--accent)]/40 text-[var(--accent)]"
              : "border-red-500/60 text-red-300"
          }`}
        >
          <span
            aria-hidden="true"
            className={`h-2 w-2 rounded-full ${connected ? "bg-[var(--accent)]" : "bg-red-400"}`}
          />
          {connected ? "Connected" : "Connection lost"}
        </span>
        <span className={`rounded-full border border-[var(--border)] px-3 py-1 ${stale ? "text-amber-300" : "muted"}`}>
          {age === null ? "No data yet" : `Data updated ${describeAge(age)}`}
          {!connected && age !== null ? " — showing the last data received" : ""}
        </span>
      </div>
    </div>
  );
}
