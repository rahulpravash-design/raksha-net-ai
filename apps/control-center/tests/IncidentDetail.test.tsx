import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Incident, StatusHistoryEntry } from "@raksha/api-client";

import { IncidentDrawer } from "@/components/command-center/IncidentDrawer";
import type { SelectedDetail } from "@/components/command-center/SelectedIncident";
import { Collapsible } from "@/components/incident/Collapsible";
import { IncidentHeader } from "@/components/incident/IncidentHeader";
import { IncidentSkeleton } from "@/components/incident/IncidentSkeleton";
import { StatusTimeline } from "@/components/incident/StatusTimeline";

vi.mock("@/lib/api", () => ({ getApiClient: () => ({}) }));

function incident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "inc-1",
    reference_code: "RKS-TEST01",
    category: "BUILDING_COLLAPSE",
    status: "REPORTED",
    severity: null,
    priority_score: 88,
    priority_band: "CRITICAL",
    priority_overridden: false,
    latitude: "13.0827",
    longitude: "80.2707",
    address_text: null,
    people_affected: 4,
    people_trapped: true,
    medical_required: true,
    immediate_danger: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    description: "Roof down, people under rubble",
    landmark: null,
    location_accuracy_m: 250,
    contact_phone: null,
    priority_factors: [],
    priority_override_reason: null,
    reported_by: null,
    assigned_to: null,
    duplicate_of_id: null,
    resolved_at: null,
    closed_at: null,
    media: [],
    ...overrides,
  };
}

const history: StatusHistoryEntry[] = [
  { id: "h1", from_status: null, to_status: "REPORTED", note: null, created_at: "2026-01-01T09:00:00Z", changed_by: null },
  { id: "h2", from_status: "REPORTED", to_status: "RECEIVED", note: "Seen", created_at: "2026-01-01T09:05:00Z", changed_by: { id: "u", full_name: "Dana Dispatcher", role: "DISPATCHER" } },
];

describe("IncidentHeader", () => {
  it("states urgent facts in words, with a glyph, and says nothing about what was not reported", () => {
    render(<IncidentHeader incident={incident()} />);
    const facts = screen.getByRole("list", { name: "Key facts" });
    expect(facts).toHaveTextContent("People trapped");
    expect(facts).toHaveTextContent("Medical support required");
    expect(facts).toHaveTextContent("4 affected");
    expect(facts).not.toHaveTextContent("Immediate danger");
    expect(facts).toHaveTextContent("Not assigned to an operator");
    expect(screen.getByText(/engine score 88/)).toBeInTheDocument();
  });

  it("says when an operator overrode the priority", () => {
    render(<IncidentHeader incident={incident({ priority_overridden: true })} />);
    expect(screen.getByText(/overridden by an operator/)).toBeInTheDocument();
  });
});

describe("Collapsible", () => {
  it("toggles with aria-expanded and removes the body when closed", async () => {
    render(
      <Collapsible title="Audit trail" summary="2 entries">
        <p>Body text</p>
      </Collapsible>,
    );
    const button = screen.getByRole("button", { name: /audit trail/i });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Body text")).toBeInTheDocument();

    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(await screen.findByText("2 entries")).toBeInTheDocument();
    await vi.waitFor(() => expect(screen.queryByText("Body text")).toBeNull());
  });

  it("can start closed", () => {
    render(
      <Collapsible title="Photographs" defaultOpen={false}>
        <p>Gallery</p>
      </Collapsible>,
    );
    expect(screen.queryByText("Gallery")).toBeNull();
  });
});

describe("StatusTimeline", () => {
  it("marks the newest entry current and names who changed it", () => {
    render(<StatusTimeline entries={history} />);
    expect(screen.getByText("Reported → Received")).toBeInTheDocument();
    expect(screen.getByText("current")).toBeInTheDocument();
    expect(screen.getByText(/Dana Dispatcher/)).toBeInTheDocument();
  });

  it("has an empty state", () => {
    render(<StatusTimeline entries={[]} />);
    expect(screen.getByText(/no recorded activity/i)).toBeInTheDocument();
  });
});

describe("IncidentSkeleton", () => {
  it("is announced as loading", () => {
    render(<IncidentSkeleton />);
    expect(screen.getByRole("status", { name: /loading incident/i })).toBeInTheDocument();
  });
});

describe("IncidentDrawer", () => {
  const detail: SelectedDetail = {
    incident: incident(),
    analysis: null,
    recommendations: [],
    history,
    loading: false,
    error: null,
  };

  it("is a modal dialog with the incident, and closes on Escape", async () => {
    const onClose = vi.fn();
    render(<IncidentDrawer open={true} detail={detail} onClose={onClose} />);

    const dialog = await screen.findByRole("dialog", { name: "Incident details" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent("Roof down, people under rubble");
    expect(dialog).toHaveTextContent(/not independently verified/i);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("moves focus to Close when opened", async () => {
    render(<IncidentDrawer open={true} detail={detail} onClose={() => {}} />);
    expect(await screen.findByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("renders nothing when closed", () => {
    render(<IncidentDrawer open={false} detail={detail} onClose={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
