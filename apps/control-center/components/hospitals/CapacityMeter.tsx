import { freeShare } from "@/lib/hospital";

/** "12 of 100 beds free" with a bar. The words carry the meaning; the bar is a hint. */
export function CapacityMeter({
  label,
  available,
  total,
}: {
  label: string;
  available: number;
  total: number;
}) {
  const share = freeShare(available, total);
  const tone = total === 0 || available === 0 ? "bg-red-400" : share < 0.15 ? "bg-amber-300" : "bg-[var(--accent)]";
  return (
    <div>
      <p className="text-sm">
        <span className="font-semibold tabular-nums">{available}</span> of{" "}
        <span className="tabular-nums">{total}</span> {label} free
        {total > 0 && available === 0 ? " — none free" : ""}
      </p>
      <div
        aria-hidden="true"
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10"
      >
        <div className={`h-full ${tone}`} style={{ width: `${Math.round(share * 100)}%` }} />
      </div>
    </div>
  );
}
