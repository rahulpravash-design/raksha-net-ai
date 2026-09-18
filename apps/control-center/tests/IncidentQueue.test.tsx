import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { IncidentSummary } from "@raksha/api-client";

import { IncidentQueue } from "@/components/IncidentQueue";

function incident(overrides: Partial<IncidentSummary> = {}): IncidentSummary {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    reference_code: "RKS-8F3K2Q",
    category: "FLOOD",
    status: "REPORTED",
    severity: null,
    priority_score: 88,
    priority_band: "CRITICAL",
    priority_overridden: false,
    latitude: "13.082700",
    longitude: "80.270700",
    address_text: "2nd Street, Kotturpuram",
    people_affected: 5,
    people_trapped: true,
    medical_required: true,
    immediate_danger: true,
    created_at: "2026-01-01T09:00:00Z",
    updated_at: "2026-01-01T09:00:00Z",
    ...overrides,
  };
}

describe("IncidentQueue", () => {
  it("shows the priority band as readable text, not only as colour", () => {
    render(
      <IncidentQueue
        incidents={[incident()]}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Critical")).toBeInTheDocument();
  });

  it("surfaces the life-safety flags a dispatcher triages on", () => {
    render(
      <IncidentQueue
        incidents={[incident()]}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Trapped")).toBeInTheDocument();
    expect(screen.getByText("Medical")).toBeInTheDocument();
  });

  it("does not show a flag that was not reported", () => {
    render(
      <IncidentQueue
        incidents={[incident({ people_trapped: false, medical_required: false })]}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.queryByText("Trapped")).not.toBeInTheDocument();
    expect(screen.queryByText("Medical")).not.toBeInTheDocument();
  });

  it("marks an overridden priority so the score is not mistaken for the engine's", () => {
    render(
      <IncidentQueue
        incidents={[incident({ priority_overridden: true })]}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Overridden")).toBeInTheDocument();
  });

  it("preserves the order the backend returned", () => {
    // The backend owns "what is most urgent". A second opinion in the client
    // would be one opinion too many.
    const rows = [
      incident({ id: "a", reference_code: "RKS-AAAAAA", priority_score: 30, priority_band: "MEDIUM" }),
      incident({ id: "b", reference_code: "RKS-BBBBBB", priority_score: 95, priority_band: "CRITICAL" }),
    ];

    render(<IncidentQueue incidents={rows} selectedId={null} onSelect={vi.fn()} />);

    const listed = screen.getAllByRole("listitem");
    expect(within(listed[0]!).getByText("RKS-AAAAAA")).toBeInTheDocument();
    expect(within(listed[1]!).getByText("RKS-BBBBBB")).toBeInTheDocument();
  });

  it("reports the selected incident to the parent", async () => {
    const onSelect = vi.fn();
    render(
      <IncidentQueue
        incidents={[incident({ id: "chosen" })]}
        selectedId={null}
        onSelect={onSelect}
      />,
    );

    await userEvent.click(screen.getByRole("button"));

    expect(onSelect).toHaveBeenCalledWith("chosen");
  });

  it("marks the selected row for assistive technology", () => {
    render(
      <IncidentQueue
        incidents={[incident({ id: "chosen" })]}
        selectedId="chosen"
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("button")).toHaveAttribute("aria-current", "true");
  });

  it("explains an empty queue rather than showing nothing", () => {
    render(<IncidentQueue incidents={[]} selectedId={null} onSelect={vi.fn()} />);

    expect(screen.getByText(/no incidents match/i)).toBeInTheDocument();
  });

  it("renders an unscored incident without crashing", () => {
    render(
      <IncidentQueue
        incidents={[incident({ priority_band: null, priority_score: null })]}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Not scored")).toBeInTheDocument();
  });
});
