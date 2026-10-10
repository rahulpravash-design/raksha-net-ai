"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Mesh, MeshBasicMaterial, Quaternion, Vector3 } from "three";

import type { PriorityBand } from "@raksha/api-client";

import { latLonToVector } from "@/lib/globe";
import { priorityTheme } from "@/lib/theme";

import { glowTexture } from "./glowTexture";

export interface GlobeMarker {
  id: string;
  lat: number;
  lon: number;
  band: PriorityBand | null;
  label: string;
}

/** How wide the glow is, by priority: the more urgent, the more it carries. */
const GLOW_SIZE: Record<string, number> = {
  CRITICAL: 0.19,
  HIGH: 0.15,
  MEDIUM: 0.12,
  LOW: 0.1,
};

/**
 * A marker on the globe: a glowing core, a selection halo, and — for critical or
 * selected incidents only — one slow expanding ring. The glow is a soft disc of
 * the priority colour lying on the surface (ordinary alpha blending, so a crowd
 * of incidents in one city saturates to that colour rather than washing out to
 * white); it breathes slowly (about 3.5 s) rather than flashing, and is steady
 * under reduced motion. The ring is a single gentle
 * cycle (2.6 s). Glow, like colour, never carries meaning alone: the priority
 * is also a glyph and a word wherever the marker is listed.
 */
export function IncidentMarker({
  marker,
  selected,
  animate,
  onSelect,
}: {
  marker: GlobeMarker;
  selected: boolean;
  animate: boolean;
  onSelect: (id: string) => void;
}) {
  const color = priorityTheme(marker.band).hex;
  const ring = useRef<Mesh>(null);
  const glow = useRef<Mesh>(null);
  const texture = useMemo(() => glowTexture(), []);
  const glowSize = GLOW_SIZE[marker.band ?? ""] ?? 0.09;
  // Markers breathe out of step with each other, not in unison.
  const breathOffset = useMemo(
    () => [...marker.id].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % 628,
    [marker.id],
  );

  const position = useMemo(() => latLonToVector(marker.lat, marker.lon, 1.012), [marker]);
  // Lay the marker's discs on the surface: local +Z points straight out of the
  // globe. Set once, in the globe's own frame, so it turns with the globe.
  const orientation = useMemo(
    () => new Quaternion().setFromUnitVectors(new Vector3(0, 0, 1), new Vector3(...position).normalize()),
    [position],
  );
  const pulses = marker.band === "CRITICAL" || selected;

  useFrame(({ clock }) => {
    if (glow.current && animate) {
      const breath = 0.78 + 0.22 * Math.sin(clock.elapsedTime * 1.8 + breathOffset / 100);
      (glow.current.material as MeshBasicMaterial).opacity = (selected ? 0.95 : 0.75) * breath;
    }
    if (!ring.current || !pulses || !animate) return;
    const phase = (clock.elapsedTime % 2.6) / 2.6;
    ring.current.scale.setScalar(0.8 + phase * 1.6);
    (ring.current.material as MeshBasicMaterial).opacity = 0.7 * (1 - phase);
  });

  return (
    <group position={position} quaternion={orientation}>
      {texture && (
        <mesh ref={glow} renderOrder={2}>
          <planeGeometry args={[glowSize * (selected ? 1.3 : 1), glowSize * (selected ? 1.3 : 1)]} />
          <meshBasicMaterial
            map={texture}
            color={color}
            transparent
            opacity={0.75}
            depthWrite={false}
          />
        </mesh>
      )}
      <mesh>
        <sphereGeometry args={[selected ? 0.02 : 0.013, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {selected && (
        <mesh>
          <ringGeometry args={[0.032, 0.037, 40]} />
          <meshBasicMaterial color="#f2f7ff" transparent opacity={0.9} />
        </mesh>
      )}
      {pulses && (
        <mesh ref={ring}>
          <ringGeometry args={[0.022, 0.027, 40]} />
          <meshBasicMaterial color={color} transparent opacity={animate ? 0 : 0.5} />
        </mesh>
      )}
      {/* A larger invisible target: the visible core is far too small to hit. */}
      <mesh
        onClick={(event) => {
          event.stopPropagation();
          onSelect(marker.id);
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "")}
      >
        <sphereGeometry args={[0.05, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}
