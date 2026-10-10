/**
 * Placeholder while the incident loads. `motion-safe:` keeps the shimmer off for
 * users who ask for reduced motion; the blocks remain as a static outline.
 */
function Block({ className }: { className: string }) {
  return (
    <div
      aria-hidden="true"
      className={`rounded-lg bg-white/5 motion-safe:animate-pulse ${className}`}
    />
  );
}

export function IncidentSkeleton() {
  return (
    <div role="status" aria-label="Loading incident" className="space-y-4">
      <Block className="h-5 w-40" />
      <div className="space-y-3">
        <Block className="h-9 w-72" />
        <div className="flex gap-2">
          <Block className="h-7 w-24" />
          <Block className="h-7 w-28" />
          <Block className="h-7 w-20" />
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Block className="h-56" />
          <Block className="h-40" />
          <Block className="h-28" />
        </div>
        <div className="space-y-4">
          <Block className="h-48" />
          <Block className="h-64" />
        </div>
      </div>
      <span className="sr-only">Loading incident…</span>
    </div>
  );
}
