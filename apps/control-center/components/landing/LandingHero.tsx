"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { canViewIncidents, roleLabel } from "@raksha/api-client";

import { GlobeStage } from "@/components/3d/GlobeStage";
import { useAuth } from "@/components/AuthProvider";
import { CITIZEN_APP_URL } from "@/lib/config";
import { globeMode, primaryAction } from "@/lib/landing";
import { incidentMarkers } from "@/lib/markers";
import { useMediaQuery } from "@/lib/useMediaQuery";

import { DEMO_ARCS, DEMO_MARKERS } from "./demoData";
import { DemoMarkerPanel } from "./DemoMarkerPanel";
import { LiveIncidentPanel } from "./LiveIncidentPanel";
import { useLiveIncidents } from "./useLiveIncidents";

const rise = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
};

export function LandingHero() {
  const { user, loading } = useAuth();
  const mode = globeMode(user, loading);
  const live = useLiveIncidents(mode === "live");
  const [chosenId, setChosenId] = useState<string | null>(null);

  // Live: the platform's open incidents. Demo: labelled demonstration markers.
  // Neither is ever mixed with the other, and nothing is drawn while the
  // session is still being read.
  const markers = useMemo(
    () =>
      mode === "live"
        ? incidentMarkers(live.incidents)
        : mode === "demo"
          ? DEMO_MARKERS
          : [],
    [mode, live.incidents],
  );
  // Arcs between demonstration cities are illustration. Between real incidents
  // they would be an invented relationship, so the live globe draws none.
  const arcs = mode === "demo" ? DEMO_ARCS : [];
  // A selection from the other mode (or a vanished incident) is dropped.
  const selectedId = markers.some((m) => m.id === chosenId) ? chosenId : null;
  const action = primaryAction(user);
  // Wide: behind the copy. Narrow: its own block, so the incident list never
  // sits on top of it. (`true` is what the server renders; the real answer follows.)
  const wide = useMediaQuery("(min-width: 1024px)", true);

  const globe = (
    <GlobeStage
      label={
        mode === "live"
          ? `Globe showing ${markers.length} open incident${markers.length === 1 ? "" : "s"} from the platform`
          : "Decorative globe with illustrative markers"
      }
      markers={markers}
      arcs={arcs}
      selectedId={selectedId}
      onSelect={setChosenId}
      focusLon={78}
    />
  );

  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--background)]">
      <div aria-hidden="true" className="grid-backdrop absolute inset-0 opacity-60" />

      {/* Wide screens: the globe sits behind the copy. Its container is a sibling
          of the content, so it never covers a link or a form field. */}
      {wide && (
        <div className="absolute inset-0 left-[40%]" data-testid="globe-stage">
          {globe}
        </div>
      )}
      {wide && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-r from-[var(--background)] via-transparent to-transparent"
        />
      )}

      <div className="pointer-events-none relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col justify-between px-5 py-8 sm:px-8">
        <header className="pointer-events-auto flex items-center justify-between">
          <span className="font-bold tracking-tight">
            RAKSHA<span className="text-[var(--accent)]"> NET AI</span>
          </span>
          {user ? (
            <span className="text-sm">
              {user.full_name} <span className="muted">· {roleLabel(user.role)}</span>
            </span>
          ) : (
            <Link href="/login" className="text-sm font-semibold underline-offset-4 hover:underline">
              Operator sign in
            </Link>
          )}
        </header>

        <main id="main" className="max-w-xl py-16">
          <motion.p
            {...rise}
            className="text-xs font-semibold uppercase tracking-[0.25em] text-[var(--accent)]"
          >
            AI-powered emergency response &amp; resource coordination
          </motion.p>
          <motion.h1
            {...rise}
            transition={{ delay: 0.06 }}
            className="mt-4 text-5xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl"
          >
            EVERY SECOND MATTERS.
          </motion.h1>
          <motion.h2
            {...rise}
            transition={{ delay: 0.12 }}
            className="mt-4 text-lg font-semibold tracking-wide text-[var(--accent)] sm:text-xl"
          >
            INTELLIGENCE THAT MOVES RESCUE FORWARD.
          </motion.h2>
          <motion.p
            {...rise}
            transition={{ delay: 0.18 }}
            className="muted mt-5 max-w-lg text-base leading-relaxed"
          >
            An AI-assisted emergency response platform connecting incident reporting,
            geospatial intelligence, and coordinated emergency resources.
          </motion.p>

          <motion.div
            {...rise}
            transition={{ delay: 0.24 }}
            className="pointer-events-auto mt-8 flex flex-wrap gap-3"
          >
            <Link
              href={action.href}
              className="rounded-lg bg-[var(--accent)] px-6 py-3 text-sm font-bold tracking-wide text-[#050914] transition hover:brightness-110"
            >
              {action.label}
            </Link>
            <a
              href={`${CITIZEN_APP_URL}/report`}
              className="rounded-lg border border-[var(--accent)]/60 px-6 py-3 text-sm font-bold tracking-wide transition hover:bg-[var(--accent)]/10"
            >
              REPORT AN EMERGENCY
            </a>
          </motion.div>

          <p className="muted mt-6 text-xs">
            AI here is decision support. Every dispatch is approved by a trained human operator.
          </p>
        </main>

        {!wide && (
          <div
            className="pointer-events-auto relative -mx-5 h-80 sm:-mx-8"
            data-testid="globe-stage"
          >
            {globe}
          </div>
        )}

        {mode === "live" ? (
          <LiveIncidentPanel live={live} selectedId={selectedId} onSelect={setChosenId} />
        ) : mode === "demo" ? (
          <DemoMarkerPanel
            selectedId={selectedId}
            onSelect={setChosenId}
            note={
              user && !canViewIncidents(user.role)
                ? "Live incident locations are limited to dispatch staff."
                : "Dispatch staff: sign in to see live incidents on the globe."
            }
          />
        ) : (
          <div className="pb-2" aria-hidden="true" />
        )}
      </div>
    </div>
  );
}
