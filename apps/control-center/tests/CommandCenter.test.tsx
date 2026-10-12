import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Incident, IncidentAnalysis } from "@raksha/api-client";

import { GlobeStage } from "@/components/3d/GlobeStage";
import { CommandStrip } from "@/components/command-center/CommandStrip";
import { SelectedIncident, type SelectedDetail } from "@/components/command-center/SelectedIncident";
import { MapLegend } from "@/components/maps/MapLegend";

vi.mock("@/lib/api", () => ({ getApiClient: () => ({}) }));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("CommandStrip", () => {
  it("reports a lost connection and that the data on screen is old", () => {
    render(<CommandStrip connected={false} lastUpdated={Date.now() - 120_000} />);
    expect(screen.getByText("Connection lost")).toBeInTheDocument();
    expect(screen.getByText(/showing the last data received/i)).toBeInTheDocument();
    expect(screen.getByText(/2 min ago/)).toBeInTheDocument();
  });

  it("does not claim freshness before any data has arrived", () => {
    render(<CommandStrip connected={true} lastUpdated={null} />);
    expect(screen.getByText("No data yet")).toBeInTheDocument();
  });
});

describe("MapLegend", () => {
  it("names every priority in words, not colour alone", () => {
    render(<MapLegend showResources={true} />);
    for (const word of ["Critical", "High", "Medium", "Low", "Available", "Committed"]) {
      expect(screen.getByText(new RegExp(word))).toBeInTheDocument();
    }
  });

  it("omits resource entries when the layer is off", () => {
    render(<MapLegend showResources={false} />);
    expect(screen.queryByText(/Available/)).toBeNull();
  });
});

describe("GlobeStage", () => {
  it("falls back to a static globe when WebGL is unavailable", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    // jsdom has no matchMedia; real browsers always do.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
    }));
    render(
      <GlobeStage label="Test globe" markers={[]} selectedId={null} onSelect={() => {}} />,
    );
    await waitFor(() => expect(screen.getByRole("img", { name: "Test globe" })).toBeInTheDocument());
    expect(document.querySelector("canvas")).toBeNull();
  });
});

function detail(overrides: Partial<SelectedDetail> = {}): SelectedDetail {
  const incident = {
    id: "inc-1",
    reference_code: "RKS-TEST01",
    category: "FLOOD",
    status: "REPORTED",
    priority_band: "CRITICAL",
    priority_score: 81,
    description: "Water rising fast",
    created_at: new Date().toISOString(),
    priority_factors: [{ key: "cat", label: "Incident category: Flood", points: 25 }],
  } as unknown as Incident;
  return {
    incident,
    analysis: null,
    recommendations: [],
    history: [],
    loading: false,
    error: null,
    ...overrides,
  };
}

describe("SelectedIncident", () => {
  it("keeps the engine score, the AI proposal and the human decision apart", () => {
    const analysis = {
      proposed_category: "FLOOD",
      proposed_severity: "HIGH",
      type_confidence: 0.6,
      review_decision: null,
      model_name: "raksha-heuristic-text-analyzer",
      model_version: "0.1.0",
    } as unknown as IncidentAnalysis;
    render(<SelectedIncident id="inc-1" detail={detail({ analysis })} />);

    expect(screen.getByText(/engine score 81/i)).toBeInTheDocument();
    expect(screen.getByText(/ai proposal — not verified/i)).toBeInTheDocument();
    expect(screen.getByText(/awaiting operator review/i)).toBeInTheDocument();
    expect(screen.getByText(/raksha-heuristic-text-analyzer v0.1.0/)).toBeInTheDocument();
  });

  it("offers no way to dispatch from the summary", () => {
    render(<SelectedIncident id="inc-1" detail={detail()} />);
    expect(screen.queryByRole("button", { name: /dispatch/i })).toBeNull();
    expect(screen.getByRole("link", { name: /open incident console/i })).toHaveAttribute(
      "href",
      "/incidents/inc-1",
    );
    expect(screen.getByText(/dispatch is a human decision/i)).toBeInTheDocument();
  });

  it("shows an API failure instead of an empty card", () => {
    render(
      <SelectedIncident
        id="inc-1"
        detail={detail({ incident: null, error: "The system is very busy." })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/very busy/i);
  });
});
