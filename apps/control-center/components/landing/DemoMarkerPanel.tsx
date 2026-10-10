import { PRIORITY_THEME } from "@/lib/theme";

import { DEMO_MARKERS } from "./demoData";

/**
 * The public page's markers: real city coordinates, invented priorities, and
 * labelled as exactly that. `note` says what a signed-in operator would see
 * instead, or why this viewer does not.
 */
export function DemoMarkerPanel({
  selectedId,
  onSelect,
  note,
}: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  note: string;
}) {
  const selected = DEMO_MARKERS.find((m) => m.id === selectedId) ?? null;

  return (
    <section
      aria-label="Globe markers (demonstration data)"
      className="pointer-events-auto max-w-xl pb-2"
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">
        Demonstration markers — not live incidents
      </p>
      <p className="muted mt-1 text-xs">
        Real city locations with illustrative priority levels, shown to preview the visuals.
        The globe is decorative; the operational map uses real map data. {note}
      </p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {DEMO_MARKERS.map((marker) => {
          const theme = PRIORITY_THEME[marker.band ?? "NONE"];
          const active = marker.id === selectedId;
          return (
            <li key={marker.id}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(active ? null : marker.id)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  active
                    ? "border-[var(--accent)] bg-[var(--accent)]/15"
                    : "border-[var(--border)] hover:border-[var(--accent)]/50"
                }`}
              >
                <span aria-hidden="true" style={{ color: theme.hex }}>
                  {theme.glyph}
                </span>{" "}
                {marker.label} · {theme.label}
              </button>
            </li>
          );
        })}
      </ul>
      <p aria-live="polite" className="mt-2 min-h-5 text-sm">
        {selected
          ? `${selected.label}: illustrative ${PRIORITY_THEME[selected.band ?? "NONE"].label.toLowerCase()}-priority marker (demonstration).`
          : ""}
      </p>
    </section>
  );
}
