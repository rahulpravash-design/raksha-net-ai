"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Group, Mesh, MeshBasicMaterial, Vector3 } from "three";

import type { PriorityBand } from "@raksha/api-client";

import { latLonToVector } from "@/lib/globe";
import { priorityTheme } from "@/lib/theme";

export interface GlobeMarker {
  id: string;
  lat: number;
  lon: number;
  band: PriorityBand | null;
  label: string;
}

/**
 * A marker on the globe: a core, a selection halo, and — for critical or
 * selected incidents only — one slow expanding ring. The ring is a single gentle
 * cycle (2.6 s), never a flash, and is absent under reduced motion.
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
  const group = useRef<Group>(null);
  const ring = useRef<Mesh>(null);

  const position = useMemo(() => latLonToVector(marker.lat, marker.lon, 1.012), [marker]);
  const outward = useMemo(() => new Vector3(...position).multiplyScalar(2), [position]);
  const pulses = marker.band === "CRITICAL" || selected;

  useFrame(({ clock }) => {
    group.current?.lookAt(outward);
    if (!ring.current || !pulses || !animate) return;
    const phase = (clock.elapsedTime % 2.6) / 2.6;
    ring.current.scale.setScalar(0.8 + phase * 1.6);
    (ring.current.material as MeshBasicMaterial).opacity = 0.7 * (1 - phase);
  });

  return (
    <group ref={group} position={position}>
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
