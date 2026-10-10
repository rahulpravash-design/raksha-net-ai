"use client";

import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { Component, useEffect, useState, type ReactNode } from "react";

import type { EarthSceneProps } from "./EarthScene";

const EarthScene = dynamic(() => import("./EarthScene"), {
  ssr: false,
  loading: () => <GlobeFallback label="Loading the globe" />,
});

/** True when the browser can create a WebGL context at all. */
export function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/** Static stand-in: a plain graticule globe in SVG. Needs no WebGL or JavaScript state. */
export function GlobeFallback({ label }: { label: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      className="flex h-full w-full items-center justify-center"
    >
      <svg viewBox="-110 -110 220 220" className="h-full max-h-[34rem] w-full max-w-[34rem]">
        <defs>
          <radialGradient id="globe-fill" cx="35%" cy="30%" r="80%">
            <stop offset="0%" stopColor="#12304d" />
            <stop offset="100%" stopColor="#050914" />
          </radialGradient>
        </defs>
        <circle r="100" fill="url(#globe-fill)" stroke="#00e5ff" strokeOpacity="0.45" />
        {[-60, -30, 0, 30, 60].map((lat) => {
          const y = Math.sin((lat * Math.PI) / 180) * 100;
          const rx = Math.cos((lat * Math.PI) / 180) * 100;
          return (
            <ellipse key={lat} cy={y} rx={rx} ry={rx * 0.12} fill="none" stroke="#3285ff" strokeOpacity="0.25" />
          );
        })}
        {[0, 30, 60, 90, 120, 150].map((lon) => (
          <ellipse key={lon} rx={Math.abs(Math.cos((lon * Math.PI) / 180)) * 100} ry="100" fill="none" stroke="#3285ff" strokeOpacity="0.25" />
        ))}
      </svg>
    </div>
  );
}

class SceneBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/**
 * Chooses between the real scene and the fallback. The page works either way:
 * the 3D globe is decoration plus a marker overview, never the only way to
 * reach anything.
 */
export function GlobeStage(
  props: Omit<EarthSceneProps, "reducedMotion" | "lowPower"> & { label: string },
) {
  const reduced = useReducedMotion() ?? false;
  const [mode, setMode] = useState<"checking" | "webgl" | "fallback">("checking");
  const [lowPower, setLowPower] = useState(false);

  useEffect(() => {
    // Browser capability checks cannot run during server rendering.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMode(webglAvailable() ? "webgl" : "fallback");
    setLowPower(
      window.matchMedia("(max-width: 767px)").matches ||
        (navigator.hardwareConcurrency ?? 8) <= 4,
    );
  }, []);

  const fallback = <GlobeFallback label={props.label} />;
  if (mode === "checking") return fallback;
  if (mode === "fallback") return fallback;

  const { label: _label, ...sceneProps } = props;
  return (
    <SceneBoundary fallback={fallback}>
      <EarthScene {...sceneProps} reducedMotion={reduced} lowPower={lowPower} />
    </SceneBoundary>
  );
}
