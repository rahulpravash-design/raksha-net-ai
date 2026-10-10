"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import { GlobeStage } from "@/components/3d/GlobeStage";
import { PRIORITY_THEME } from "@/lib/theme";
import { CITIZEN_APP_URL } from "@/lib/config";

import { DEMO_ARCS, DEMO_MARKERS } from "./demoData";

const rise = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
};

export function LandingHero() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = DEMO_MARKERS.find((m) => m.id === selectedId) ?? null;

  return (
    <div className="relative min-h-screen overflow-hidden bg-[var(--background)]">
      <div aria-hidden="true" className="grid-backdrop absolute inset-0 opacity-60" />

      {/* The globe sits behind the copy. Its container is a sibling of the
          content, so it never covers a link or a form field. */}
      <div
        className="absolute inset-x-0 bottom-0 top-[42%] lg:inset-0 lg:left-[40%]"
        data-testid="globe-stage"
      >
        <GlobeStage
          label="Decorative globe with illustrative markers"
          markers={DEMO_MARKERS}
          arcs={DEMO_ARCS}
          selectedId={selectedId}
          onSelect={setSelectedId}
          focusLon={78}
        />
      </div>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[var(--background)] via-[var(--background)]/85 to-transparent lg:bg-gradient-to-r lg:via-transparent"
      />

      <div className="pointer-events-none relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col justify-between px-5 py-8 sm:px-8">
        <header className="pointer-events-auto flex items-center justify-between">
          <span className="font-bold tracking-tight">
            RAKSHA<span className="text-[var(--accent)]"> NET AI</span>
          </span>
          <Link href="/login" className="text-sm font-semibold underline-offset-4 hover:underline">
            Operator sign in
          </Link>
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
              href="/dashboard"
              className="rounded-lg bg-[var(--accent)] px-6 py-3 text-sm font-bold tracking-wide text-[#050914] transition hover:brightness-110"
            >
              ENTER COMMAND CENTER
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

        <section
          aria-label="Globe markers (demonstration data)"
          className="pointer-events-auto max-w-xl pb-2"
        >
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">
            Demonstration markers — not live incidents
          </p>
          <p className="muted mt-1 text-xs">
            Real city locations with illustrative priority levels, shown to preview the
            visuals. The globe is decorative; the operational map uses real map data.
          </p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {DEMO_MARKERS.map((marker) => {
              const theme = PRIORITY_THEME[marker.band ?? "NONE"];
              const active = marker.id === selectedId;
              return (
                <li key={marker.id}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSelectedId(active ? null : marker.id)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                      active
                        ? "border-[var(--accent)] bg-[var(--accent)]/15"
                        : "border-[var(--border)] hover:border-[var(--accent)]/50"
                    }`}
                  >
                    <span aria-hidden="true" style={{ color: theme.hex }}>
                      {theme.glyph}
                    </span>{" "}
                    {marker.label} · {theme.label}
                  </button>
                </li>
              );
            })}
          </ul>
          <p aria-live="polite" className="mt-2 min-h-5 text-sm">
            {selected
              ? `${selected.label}: illustrative ${PRIORITY_THEME[selected.band ?? "NONE"].label.toLowerCase()}-priority marker (demonstration).`
              : ""}
          </p>
        </section>
      </div>
    </div>
  );
}
