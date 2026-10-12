"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import {
  BufferGeometry,
  Float32BufferAttribute,
  Group,
  LineBasicMaterial,
  LineSegments,
} from "three";

import { landPoints, latLonToVector } from "@/lib/globe";
import { COLORS } from "@/lib/theme";

import { ConnectionArc } from "./ConnectionArc";
import { EarthAtmosphere } from "./EarthAtmosphere";
import { IncidentMarker, type GlobeMarker } from "./IncidentMarker";
import { buildLandMask } from "./landMask";

export type { GlobeMarker };

export interface GlobeArc {
  from: string;
  to: string;
}

export interface EarthSceneProps {
  markers: GlobeMarker[];
  arcs?: GlobeArc[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** Respect the user's reduced-motion setting: no rotation, no pulses. */
  reducedMotion: boolean;
  /** Fewer points and a lower pixel ratio, for phones and weak GPUs. */
  lowPower: boolean;
  /** Longitude (degrees) the globe starts facing, so the scene opens on the data. */
  focusLon?: number;
}

function graticule(): LineSegments {
  const positions: number[] = [];
  const push = (a: [number, number, number], b: [number, number, number]) =>
    positions.push(...a, ...b);
  for (let lat = -60; lat <= 60; lat += 30) {
    for (let lon = -180; lon < 180; lon += 6) {
      push(latLonToVector(lat, lon, 1.002), latLonToVector(lat, lon + 6, 1.002));
    }
  }
  for (let lon = -180; lon < 180; lon += 30) {
    for (let lat = -84; lat < 84; lat += 6) {
      push(latLonToVector(lat, lon, 1.002), latLonToVector(lat + 6, lon, 1.002));
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  return new LineSegments(
    geometry,
    new LineBasicMaterial({ color: COLORS.blue, transparent: true, opacity: 0.16 }),
  );
}

/** Slow turn, with a little drag-to-rotate, around a fixed vertical axis. */
function Globe({
  markers,
  arcs,
  selectedId,
  onSelect,
  reducedMotion,
  lowPower,
  focusLon = 0,
}: EarthSceneProps) {
  const spin = useRef<Group>(null);
  const drag = useRef({ active: false, x: 0, y: 0, tilt: 0.35, yaw: -(focusLon + 90) * (Math.PI / 180) });

  const grid = useMemo(() => graticule(), []);
  const land = useMemo(() => {
    const mask = buildLandMask();
    return mask ? landPoints(mask, lowPower ? 30000 : 90000, 1.003) : new Float32Array();
  }, [lowPower]);

  const byId = useMemo(() => new Map(markers.map((m) => [m.id, m])), [markers]);
  const arcSpecs = useMemo(
    () =>
      (arcs ?? []).flatMap((arc) => {
        const from = byId.get(arc.from);
        const to = byId.get(arc.to);
        return from && to ? [{ key: `${arc.from}-${arc.to}`, from, to }] : [];
      }),
    [arcs, byId],
  );

  useFrame((_, delta) => {
    const group = spin.current;
    if (!group) return;
    if (!drag.current.active && !reducedMotion) drag.current.yaw += delta * 0.05;
    group.rotation.y = drag.current.yaw;
    group.rotation.x = drag.current.tilt;
  });

  return (
    <group
      ref={spin}
      onPointerDown={(e) => {
        drag.current.active = true;
        drag.current.x = e.clientX;
        drag.current.y = e.clientY;
      }}
      onPointerMove={(e) => {
        if (!drag.current.active) return;
        drag.current.yaw += (e.clientX - drag.current.x) * 0.005;
        drag.current.tilt = Math.max(
          -0.9,
          Math.min(0.9, drag.current.tilt + (e.clientY - drag.current.y) * 0.003),
        );
        drag.current.x = e.clientX;
        drag.current.y = e.clientY;
      }}
      onPointerUp={() => (drag.current.active = false)}
      onPointerLeave={() => (drag.current.active = false)}
      onPointerMissed={() => onSelect(null)}
    >
      {/* Opaque core: hides the far-side land dots. */}
      <mesh>
        <sphereGeometry args={[0.994, 64, 64]} />
        <meshBasicMaterial color="#071326" />
      </mesh>
      <primitive object={grid} />
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[land, 3]} />
        </bufferGeometry>
        <pointsMaterial
          color={COLORS.cyan}
          size={lowPower ? 0.008 : 0.0055}
          sizeAttenuation
          transparent
          opacity={0.85}
          depthWrite={false}
        />
      </points>

      {arcSpecs.map((arc, index) => (
        <ConnectionArc
          key={arc.key}
          from={arc.from}
          to={arc.to}
          color={COLORS.cyan}
          animate={!reducedMotion}
          offset={index / Math.max(1, arcSpecs.length)}
        />
      ))}

      {markers.map((marker) => (
        <IncidentMarker
          key={marker.id}
          marker={marker}
          selected={marker.id === selectedId}
          animate={!reducedMotion}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}

/** Gentle pointer parallax on the camera; none under reduced motion. */
function CameraRig({ enabled }: { enabled: boolean }) {
  useFrame(({ pointer, camera }) => {
    if (!enabled) return;
    camera.position.x += (pointer.x * 0.25 - camera.position.x) * 0.04;
    camera.position.y += (pointer.y * 0.18 - camera.position.y) * 0.04;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

/**
 * The decorative Earth. It is not a navigation map: coordinates are shown only
 * as markers the caller supplies, and the operational map is a separate
 * component backed by real map tiles.
 */
export default function EarthScene(props: EarthSceneProps) {
  const { reducedMotion, lowPower } = props;
  return (
    <Canvas
      camera={{ position: [0, 0, 3.5], fov: 42 }}
      dpr={lowPower ? 1 : [1, 1.75]}
      frameloop={reducedMotion ? "demand" : "always"}
      gl={{ antialias: !lowPower, alpha: true, powerPreference: "high-performance" }}
      // `pan-y`: a vertical swipe on the globe still scrolls the page.
      style={{ touchAction: "pan-y" }}
      aria-hidden="true"
    >
      <CameraRig enabled={!reducedMotion && !lowPower} />
      <Globe {...props} />
      <EarthAtmosphere />
    </Canvas>
  );
}

