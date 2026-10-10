"use client";

import { motion } from "motion/react";

import { formatRelative, type Hospital } from "@raksha/api-client";

import { isCapacityStale } from "@/lib/hospital";

import { CapacityMeter } from "./CapacityMeter";

export function AcceptingTag({ accepting }: { accepting: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
        accepting ? "border-[var(--accent)]/50 text-[var(--accent)]" : "border-red-400/60 text-red-300"
      }`}
    >
      <span aria-hidden="true">{accepting ? "●" : "✕"}</span>
      {accepting ? "Accepting emergencies" : "Not accepting"}
    </span>
  );
}

export function HospitalCard({
  hospital,
  selected,
  mine,
  index,
  onSelect,
}: {
  hospital: Hospital;
  selected: boolean;
  mine: boolean;
  index: number;
  onSelect: () => void;
}) {
  const stale = isCapacityStale(hospital.capacity_updated_at);
  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.03 }}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected ? "true" : undefined}
        className={`panel-3d w-full space-y-2 rounded-xl p-3 text-left ${selected ? "border-[var(--accent)]!" : ""}`}
      >
        <span className="flex items-start justify-between gap-2">
          <span>
            <span className="block font-semibold">{hospital.name}</span>
            <span className="muted block text-xs">
              {hospital.code}
              {mine ? " · your hospital" : ""}
            </span>
          </span>
          <AcceptingTag accepting={hospital.accepting_emergencies} />
        </span>
        <span className="block space-y-2">
          <CapacityMeter label="beds" available={hospital.available_beds} total={hospital.total_beds} />
          <CapacityMeter label="ICU beds" available={hospital.icu_available} total={hospital.icu_total} />
        </span>
        <span className={`block text-xs ${stale ? "text-amber-300" : "muted"}`}>
          {hospital.capacity_updated_at
            ? `Reported ${formatRelative(hospital.capacity_updated_at)}${stale ? " — may be out of date" : ""}`
            : "Capacity never reported"}
        </span>
      </button>
    </motion.li>
  );
}
