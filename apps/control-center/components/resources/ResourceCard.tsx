"use client";

import { motion } from "motion/react";

import { formatRelative, resourceTypeLabel, type Resource } from "@raksha/api-client";

import { ResourceStatusTag } from "./ResourceStatusTag";

export function ResourceCard({
  resource,
  selected,
  index,
  onSelect,
}: {
  resource: Resource;
  selected: boolean;
  index: number;
  onSelect: () => void;
}) {
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
        className={`panel-3d w-full rounded-xl p-3 text-left ${
          selected ? "border-[var(--accent)]!" : ""
        } ${resource.is_active ? "" : "opacity-60"}`}
      >
        <span className="flex items-start justify-between gap-2">
          <span>
            <span className="block font-semibold">{resource.call_sign}</span>
            <span className="muted block text-xs">{resource.name}</span>
          </span>
          <ResourceStatusTag status={resource.status} />
        </span>
        <span className="muted mt-2 block text-xs">
          {resourceTypeLabel(resource.resource_type)}
          {resource.crew_size !== null ? ` · crew ${resource.crew_size}` : ""}
          {!resource.is_active ? " · deactivated" : ""}
          {resource.status_changed_at
            ? ` · status ${formatRelative(resource.status_changed_at)}`
            : ""}
        </span>
        {resource.capabilities.length > 0 && (
          <span className="mt-2 flex flex-wrap gap-1">
            {resource.capabilities.slice(0, 4).map((capability) => (
              <span
                key={capability}
                className="rounded border border-[var(--border)] px-1.5 py-0.5 text-[0.7rem]"
              >
                {capability}
              </span>
            ))}
            {resource.capabilities.length > 4 && (
              <span className="muted text-[0.7rem]">+{resource.capabilities.length - 4}</span>
            )}
          </span>
        )}
      </button>
    </motion.li>
  );
}
