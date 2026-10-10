"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, type IncidentSummary } from "@raksha/api-client";

import { getApiClient } from "@/lib/api";

/** How many open incidents the globe draws. Past this, the highest priority win. */
export const LIVE_MARKER_LIMIT = 50;
export const LIVE_REFRESH_MS = 15_000;

export interface LiveIncidents {
  /** `loading` until the first answer; `unavailable` if there has never been one. */
  state: "idle" | "loading" | "ready" | "unavailable";
  incidents: IncidentSummary[];
  /** The platform's own count of open incidents (may exceed what is drawn). */
  totalOpen: number | null;
  lastUpdated: number | null;
  /** False once a refresh has failed, until one succeeds again. */
  connected: boolean;
}

const IDLE: LiveIncidents = {
  state: "idle",
  incidents: [],
  totalOpen: null,
  lastUpdated: null,
  connected: true,
};

/**
 * Open incidents for the landing globe, from the same endpoints the command
 * centre uses. Only enabled for a signed-in dispatch-side user: the API refuses
 * everyone else, and the landing page is public, so nothing is fetched or shown
 * for a visitor. A failed refresh keeps the last data and says the connection is
 * lost; it never invents data.
 */
export function useLiveIncidents(enabled: boolean): LiveIncidents {
  const [live, setLive] = useState<LiveIncidents>(IDLE);

  const refresh = useCallback(async () => {
    const api = getApiClient();
    try {
      const [page, stats] = await Promise.all([
        api.incidentQueue({ open_only: true, sort: "priority", page_size: LIVE_MARKER_LIMIT }),
        api.incidentStats(),
      ]);
      setLive({
        state: "ready",
        incidents: page.items,
        totalOpen: stats.total_open,
        lastUpdated: Date.now(),
        connected: true,
      });
    } catch (caught) {
      // A 401 means the session ended; the auth layer handles that.
      if (caught instanceof ApiError && caught.status === 401) return;
      setLive((previous) => ({
        ...previous,
        state: previous.state === "ready" ? "ready" : "unavailable",
        connected: false,
      }));
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      // Signed out or not a dispatch-side role: drop whatever was held.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLive(IDLE);
      return;
    }
    setLive((previous) => (previous.state === "idle" ? { ...previous, state: "loading" } : previous));
    void refresh();
    const timer = window.setInterval(() => void refresh(), LIVE_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [enabled, refresh]);

  return live;
}
