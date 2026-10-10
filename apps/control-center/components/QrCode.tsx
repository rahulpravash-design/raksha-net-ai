"use client";

import QRCode from "qrcode";
import { useMemo } from "react";

const QUIET_ZONE = 4;

/**
 * A QR code drawn as one SVG path. Built from the library's module matrix rather
 * than injected markup, so nothing here parses a string as HTML. Always dark on
 * white with the standard 4-module quiet zone — authenticator apps will not read
 * a themed or inverted code.
 */
export function QrCode({ value, label }: { value: string; label: string }) {
  const { size, path } = useMemo(() => {
    const qr = QRCode.create(value, { errorCorrectionLevel: "M" });
    const count = qr.modules.size;
    let d = "";
    for (let row = 0; row < count; row++) {
      for (let col = 0; col < count; col++) {
        if (qr.modules.get(row, col)) d += `M${col + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`;
      }
    }
    return { size: count + QUIET_ZONE * 2, path: d };
  }, [value]);

  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${size} ${size}`}
      shapeRendering="crispEdges"
      className="h-48 w-48 rounded-lg bg-white"
    >
      <path d={path} fill="#000" />
    </svg>
  );
}
