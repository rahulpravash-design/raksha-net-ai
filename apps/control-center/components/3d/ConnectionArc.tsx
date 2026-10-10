"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { BufferGeometry, Float32BufferAttribute, Line, LineBasicMaterial, Mesh } from "three";

import { greatCircleArc } from "@/lib/globe";

/**
 * A faint arc between two displayed coordinates, with one small light travelling
 * along it when motion is allowed. Purely illustrative: it conveys that the
 * platform coordinates between places, not that any specific unit is moving.
 */
export function ConnectionArc({
  from,
  to,
  color,
  animate,
  offset = 0,
}: {
  from: { lat: number; lon: number };
  to: { lat: number; lon: number };
  color: string;
  animate: boolean;
  offset?: number;
}) {
  const points = useMemo(() => greatCircleArc(from, to, 56, 0.22), [from, to]);
  const line = useMemo(() => {
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(points.flat(), 3));
    return new Line(
      geometry,
      new LineBasicMaterial({ color, transparent: true, opacity: 0.55 }),
    );
  }, [points, color]);

  const spark = useRef<Mesh>(null);
  useFrame(({ clock }) => {
    if (!spark.current || !animate) return;
    const t = ((clock.elapsedTime / 5 + offset) % 1) * (points.length - 1);
    const p = points[Math.floor(t)];
    if (p) spark.current.position.set(p[0], p[1], p[2]);
  });

  return (
    <>
      <primitive object={line} />
      {animate && (
        <mesh ref={spark}>
          <sphereGeometry args={[0.007, 8, 8]} />
          <meshBasicMaterial color="#f2f7ff" />
        </mesh>
      )}
    </>
  );
}
