export type MapView = "map" | "globe";

/** Layer toggles and the Map / Globe switch. Plain buttons, big enough to tap. */
export function MapControls({
  view,
  onView,
  showResources,
  onShowResources,
  resourceCount,
}: {
  view: MapView;
  onView: (view: MapView) => void;
  showResources: boolean;
  onShowResources: (value: boolean) => void;
  resourceCount: number;
}) {
  const tab = (active: boolean) =>
    `rounded-md px-3 py-1.5 text-xs font-semibold transition ${
      active ? "bg-[var(--accent)] text-[#050914]" : "hover:bg-white/10"
    }`;

  return (
    <div className="panel-3d flex flex-wrap items-center gap-2 rounded-lg p-1.5">
      <div role="group" aria-label="Visualisation" className="flex gap-1">
        <button
          type="button"
          aria-pressed={view === "map"}
          className={tab(view === "map")}
          onClick={() => onView("map")}
        >
          Operational map
        </button>
        <button
          type="button"
          aria-pressed={view === "globe"}
          className={tab(view === "globe")}
          onClick={() => onView("globe")}
        >
          Globe overview
        </button>
      </div>
      {view === "map" && (
        <label className="flex items-center gap-2 px-2 text-xs">
          <input
            type="checkbox"
            checked={showResources}
            onChange={(event) => onShowResources(event.target.checked)}
          />
          Resources ({resourceCount})
        </label>
      )}
    </div>
  );
}
