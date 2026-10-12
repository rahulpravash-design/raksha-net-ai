import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { IncidentAnalysis } from "@raksha/api-client";

import { AIAnalysisPanel } from "@/components/AIAnalysisPanel";

const listAnalyses = vi.fn();
const runAnalysis = vi.fn();
const reviewAnalysis = vi.fn();

vi.mock("@/lib/api", () => ({
  getApiClient: () => ({
    listAnalyses,
    runAnalysis,
    reviewAnalysis,
  }),
}));

function proposal(overrides: Partial<IncidentAnalysis> = {}): IncidentAnalysis {
  return {
    id: "analysis-1",
    incident_id: "incident-1",
    model_name: "raksha-heuristic-text-analyzer",
    model_version: "0.1.0",
    provider: "internal-rules",
    processing_ms: 1,
    proposed_category: "FLOOD",
    type_confidence: 0.6,
    proposed_severity: "CRITICAL",
    severity_confidence: 0.55,
    people_affected: 5,
    people_trapped: true,
    medical_support_required: null,
    immediate_rescue_required: true,
    entities: {},
    observations: [],
    reasoning_factors: ["description mentions 'trapped'"],
    review_decision: null,
    reviewed_by: null,
    reviewed_at: null,
    review_note: null,
    applied_fields: null,
    created_at: "2026-01-01T09:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  listAnalyses.mockReset().mockResolvedValue([]);
  runAnalysis.mockReset();
  reviewAnalysis.mockReset();
});

describe("AIAnalysisPanel", () => {
  it("shows each observation as an AI observation, with its source and confidence", async () => {
    listAnalyses.mockResolvedValue([
      proposal({
        model_name: "raksha-heuristic-text-analyzer+claude-opus-5-5",
        observations: [
          { label: "possible_injured_person", confidence: 0.72, source: "IMAGE" },
          { label: "smoke_visible", confidence: 0.41, source: "IMAGE" },
        ],
      }),
    ]);
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);

    const list = await screen.findByRole("list", { name: /ai observations/i });
    expect(list).toHaveTextContent("Possible injured person");
    expect(list).toHaveTextContent("(photo)");
    expect(list).toHaveTextContent("72%");
    // Never presented as a fact.
    expect(screen.getByText(/not verified facts/i)).toBeInTheDocument();
    expect(list.querySelectorAll('li[title="AI observation: unverified"]')).toHaveLength(2);
  });

  it("shows no observation section when there are none", async () => {
    listAnalyses.mockResolvedValue([proposal()]);
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);
    await screen.findByText(/ai proposal/i);
    expect(screen.queryByRole("list", { name: /ai observations/i })).not.toBeInTheDocument();
  });

  it("explains that there is no proposal yet", async () => {
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);

    expect(await screen.findByText(/no ai analysis has been requested/i)).toBeInTheDocument();
  });

  it("requests an analysis when asked", async () => {
    runAnalysis.mockResolvedValue(proposal());
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);
    await screen.findByText(/no ai analysis has been requested/i);

    await userEvent.click(screen.getByRole("button", { name: /run ai analysis/i }));

    await waitFor(() => expect(runAnalysis).toHaveBeenCalledWith("incident-1"));
  });

  it("shows the proposal with its reasoning and a low-confidence marker", async () => {
    listAnalyses.mockResolvedValue([proposal()]);
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);

    expect(await screen.findByText("Flood")).toBeInTheDocument();
    expect(screen.getByText(/description mentions 'trapped'/)).toBeInTheDocument();
    // A heuristic never reaches "high confidence" in this fixture.
    expect(screen.getAllByText(/confidence/).length).toBeGreaterThan(0);
  });

  it("does not offer review controls to a non-dispatch role", async () => {
    listAnalyses.mockResolvedValue([proposal()]);
    render(<AIAnalysisPanel incidentId="incident-1" canReview={false} onApplied={vi.fn()} />);

    await screen.findByText("Flood");
    expect(screen.queryByRole("button", { name: /^accept$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/awaiting a dispatcher/i)).toBeInTheDocument();
  });

  it("accepts a proposal and notifies the parent to reload the incident", async () => {
    listAnalyses.mockResolvedValue([proposal()]);
    reviewAnalysis.mockResolvedValue(
      proposal({ review_decision: "ACCEPTED", applied_fields: { category: "FLOOD" } }),
    );
    const onApplied = vi.fn();
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={onApplied} />);

    await userEvent.click(await screen.findByRole("button", { name: /^accept$/i }));

    await waitFor(() =>
      expect(reviewAnalysis).toHaveBeenCalledWith("incident-1", "analysis-1", {
        decision: "ACCEPTED",
        note: null,
      }),
    );
    expect(onApplied).toHaveBeenCalled();
  });

  it("rejects a proposal without ever calling an incident-mutating endpoint directly", async () => {
    listAnalyses.mockResolvedValue([proposal()]);
    reviewAnalysis.mockResolvedValue(proposal({ review_decision: "REJECTED" }));
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: /^reject$/i }));

    await waitFor(() =>
      expect(reviewAnalysis).toHaveBeenCalledWith("incident-1", "analysis-1", {
        decision: "REJECTED",
        note: null,
      }),
    );
  });

  it("shows a reviewed proposal's outcome instead of the action buttons", async () => {
    listAnalyses.mockResolvedValue([
      proposal({
        review_decision: "ACCEPTED",
        reviewed_by: { id: "u1", full_name: "Karthik Subramanian", role: "DISPATCHER" },
        review_note: "Matches the photos too.",
      }),
    ]);
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);

    expect(await screen.findByText(/accepted by karthik subramanian/i)).toBeInTheDocument();
    expect(screen.getByText("Matches the photos too.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^accept$/i })).not.toBeInTheDocument();
  });

  it("lets a dispatcher edit the proposed category before saving", async () => {
    listAnalyses.mockResolvedValue([proposal()]);
    reviewAnalysis.mockResolvedValue(proposal({ review_decision: "EDITED" }));
    render(<AIAnalysisPanel incidentId="incident-1" canReview={true} onApplied={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: /^edit$/i }));
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /corrected category/i }),
      "FIRE",
    );
    await userEvent.click(screen.getByRole("button", { name: /save correction/i }));

    await waitFor(() =>
      expect(reviewAnalysis).toHaveBeenCalledWith(
        "incident-1",
        "analysis-1",
        expect.objectContaining({ decision: "EDITED", category: "FIRE" }),
      ),
    );
  });
});
