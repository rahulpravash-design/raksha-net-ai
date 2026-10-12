import { CanvasTexture } from "three";

let cached: CanvasTexture | null | undefined;

/**
 * A soft white radial falloff, tinted per marker by the material colour. Built
 * once and shared. Returns null where a 2D canvas is unavailable; a marker then
 * simply has no halo, which is a loss of decoration, not of information.
 */
export function glowTexture(): CanvasTexture | null {
  if (cached !== undefined) return cached;
  try {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 128;
    const context = canvas.getContext("2d");
    if (!context) {
      cached = null;
      return cached;
    }
    const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64);
    gradient.addColorStop(0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.18, "rgba(255,255,255,0.65)");
    gradient.addColorStop(0.45, "rgba(255,255,255,0.18)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
    cached = new CanvasTexture(canvas);
  } catch {
    cached = null;
  }
  return cached;
}
