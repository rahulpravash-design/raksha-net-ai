import type { PriorityBand } from "@raksha/api-client";

import { PRIORITY_THEME, RESOURCE_STATUS_COLOR } from "@/lib/theme";

const BANDS: PriorityBand[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

/** Every entry pairs a colour with a glyph and a word. */
export function MapLegend({ showResources }: { showResources: boolean }) {
  return (
    <details aria-label="Map legend" className="panel-3d pointer-events-auto rounded-lg px-3 py-2 text-xs">
      <summary className="cursor-pointer font-semibold">Legend</summary>
      <p className="mt-1 font-semibold">Incidents</p>
      <ul className="mt-1 space-y-0.5">
        {BANDS.map((band) => (
          <li key={band}>
            <span aria-hidden="true" style={{ color: PRIORITY_THEME[band].hex }}>
              {PRIORITY_THEME[band].glyph}
            </span>{" "}
            {PRIORITY_THEME[band].label}
          </li>
        ))}
      </ul>
      {showResources && (
        <>
          <p className="mt-2 font-semibold">Resources</p>
          <ul className="mt-1 space-y-0.5">
            <li>
              <span style={{ color: RESOURCE_STATUS_COLOR.AVAILABLE }}>▭</span> Available
            </li>
            <li>
              <span style={{ color: RESOURCE_STATUS_COLOR.DISPATCHED }}>▭</span> Committed
            </li>
            <li>
              <span style={{ color: RESOURCE_STATUS_COLOR.OUT_OF_SERVICE }}>▭</span> Out of
              service (dashed)
            </li>
          </ul>
        </>
      )}
    </details>
  );
}
