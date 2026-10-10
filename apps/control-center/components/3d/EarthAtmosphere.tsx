"use client";

import { AdditiveBlending, BackSide, Color } from "three";

const VERTEX = /* glsl */ `
  varying vec3 vNormal;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// Fresnel-style rim light: brightest where the shell is seen edge-on.
const FRAGMENT = /* glsl */ `
  uniform vec3 uColor;
  uniform float uPower;
  varying vec3 vNormal;
  void main() {
    float rim = pow(0.72 - dot(vNormal, vec3(0.0, 0.0, 1.0)), uPower);
    gl_FragColor = vec4(uColor, 1.0) * clamp(rim, 0.0, 1.0);
  }
`;

/** The thin atmospheric shell. One extra draw call; no post-processing. */
export function EarthAtmosphere({ radius = 1.14 }: { radius?: number }) {
  return (
    <mesh scale={radius}>
      <sphereGeometry args={[1, 48, 48]} />
      <shaderMaterial
        vertexShader={VERTEX}
        fragmentShader={FRAGMENT}
        uniforms={{ uColor: { value: new Color("#00e5ff") }, uPower: { value: 3.2 } }}
        side={BackSide}
        blending={AdditiveBlending}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}
