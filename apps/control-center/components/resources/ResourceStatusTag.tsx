import { resourceStatusLabel, type ResourceStatus } from "@raksha/api-client";

import { RESOURCE_STATUS_COLOR } from "@/lib/theme";

const GLYPH: Record<ResourceStatus, string> = {
  AVAILABLE: "●",
  DISPATCHED: "◆",
  EN_ROUTE: "▶",
  ON_SCENE: "■",
  OUT_OF_SERVICE: "○",
};

/** Status as glyph + word + colour, so it never depends on colour alone. */
export function ResourceStatusTag({ status }: { status: ResourceStatus }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold"
      style={{ borderColor: RESOURCE_STATUS_COLOR[status], color: RESOURCE_STATUS_COLOR[status] }}
    >
      <span aria-hidden="true">{GLYPH[status]}</span>
      {resourceStatusLabel(status)}
    </span>
  );
}
