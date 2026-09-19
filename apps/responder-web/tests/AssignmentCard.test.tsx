import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ResponderAssignment } from "@raksha/api-client";

import { AssignmentCard } from "@/components/AssignmentCard";

function assignment(
  overrides: Partial<ResponderAssignment> = {},
): ResponderAssignment {
  return {
    id: "d1",
    incident_id: "i1",
    resource_id: "r1",
    status: "DISPATCHED",
    distance_km: 2.4,
    estimated_minutes: 5,
    note: null,
    cancel_reason: null,
    approved_by: { id: "u1", full_name: "Karthik Subramanian", role: "DISPATCHER" },
    resource: {
      id: "r1",
      call_sign: "AMB-01",
      name: "Ambulance 1",
      resource_type: "AMBULANCE",
      status: "DISPATCHED",
      latitude: "13.082700",
      longitude: "80.270700",
      base_address: null,
      capabilities: [],
      crew_size: 3,
      contact_phone: null,
      is_active: true,
      operator: null,
      status_changed_at: null,
      created_at: "2026-01-01T09:00:00Z",
      updated_at: "2026-01-01T09:00:00Z",
    },
    acknowledged_at: null,
    en_route_at: null,
    on_scene_at: null,
    closed_at: null,
    created_at: "2026-01-01T09:00:00Z",
    updated_at: "2026-01-01T09:00:00Z",
    incident: {
      id: "i1",
      reference_code: "RKS-8F3K2Q",
      category: "FLOOD",
      priority_band: "CRITICAL",
      description: "Five people trapped, water rising fast.",
      latitude: 13.0827,
      longitude: 80.2707,
      address_text: "2nd Street, Kotturpuram",
      landmark: null,
      people_affected: 5,
      people_trapped: true,
      medical_required: true,
      immediate_danger: true,
      contact_phone: "+919876543210",
    },
    ...overrides,
  };
}

describe("AssignmentCard", () => {
  it("shows the priority as readable text, not only as colour", () => {
    render(<AssignmentCard assignment={assignment()} />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });

  it("surfaces the life-safety flags a crew needs before they arrive", () => {
    render(<AssignmentCard assignment={assignment()} />);
    expect(screen.getByText("People trapped")).toBeInTheDocument();
    expect(screen.getByText("Medical")).toBeInTheDocument();
    expect(screen.getByText("Immediate danger")).toBeInTheDocument();
  });

  it("does not show a flag that was not reported", () => {
    render(
      <AssignmentCard
        assignment={assignment({
          incident: { ...assignment().incident, people_trapped: false },
        })}
      />,
    );
    expect(screen.queryByText("People trapped")).not.toBeInTheDocument();
  });

  it("marks the travel figure as a direct-line estimate", () => {
    render(<AssignmentCard assignment={assignment()} />);
    expect(screen.getByText(/direct/)).toBeInTheDocument();
  });

  it("links to the assignment rather than the incident", () => {
    render(<AssignmentCard assignment={assignment()} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/assignments/d1");
  });
});
