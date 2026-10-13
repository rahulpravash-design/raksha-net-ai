import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { VoiceTranscript } from "@raksha/api-client";

import { VoiceTranscriptPanel } from "@/components/VoiceTranscriptPanel";

const listTranscripts = vi.fn();

vi.mock("@/lib/api", () => ({
  getApiClient: () => ({ listTranscripts }),
}));

function transcript(overrides: Partial<VoiceTranscript> = {}): VoiceTranscript {
  return {
    id: "t-1",
    incident_id: "incident-1",
    source: "AI_TRANSCRIPT",
    text: "Five people are trapped.",
    confidence: 0.9,
    language: "english",
    language_hint: null,
    duration_seconds: 4,
    model_name: "whisper-1",
    model_version: "1.0.0",
    provider: "openai",
    reporter_edited: false,
    created_at: "2026-01-01T09:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  listTranscripts.mockReset().mockResolvedValue([]);
});

describe("VoiceTranscriptPanel", () => {
  it("shows nothing for a report that was typed", async () => {
    const { container } = render(<VoiceTranscriptPanel incidentId="incident-1" />);

    await waitFor(() => expect(listTranscripts).toHaveBeenCalledWith("incident-1"));
    expect(container).toBeEmptyDOMElement();
  });

  it("labels the record as an AI transcript, with its model and confidence", async () => {
    listTranscripts.mockResolvedValue([transcript()]);
    render(<VoiceTranscriptPanel incidentId="incident-1" />);

    const panel = await screen.findByRole("region", { name: /dictated report/i });
    expect(panel).toHaveTextContent("AI transcript");
    expect(panel).toHaveTextContent("whisper-1 v1.0.0");
    expect(panel).toHaveTextContent("90% confidence");
    expect(panel).toHaveTextContent(/AI-derived and unverified/i);
    expect(panel).toHaveTextContent("Sent as transcribed.");
  });

  it("does not repeat the words when they are the description", async () => {
    listTranscripts.mockResolvedValue([transcript({ reporter_edited: false })]);
    render(<VoiceTranscriptPanel incidentId="incident-1" />);

    await screen.findByRole("region", { name: /dictated report/i });
    expect(screen.queryByText("Five people are trapped.")).toBeNull();
    expect(
      screen.queryByText("What the speech model heard", { selector: "summary" }),
    ).toBeNull();
  });

  it("says when the reporter corrected it, and offers what the model had heard", async () => {
    listTranscripts.mockResolvedValue([
      transcript({ reporter_edited: true, text: "Fire people are trapped." }),
    ]);
    render(<VoiceTranscriptPanel incidentId="incident-1" />);

    const panel = await screen.findByRole("region", { name: /dictated report/i });
    expect(panel).toHaveTextContent("The reporter corrected the transcript before sending.");

    await userEvent.click(
      screen.getByText("What the speech model heard", { selector: "summary" }),
    );
    expect(screen.getByText("Fire people are trapped.")).toBeVisible();
  });

  it("notes the language the recogniser heard", async () => {
    listTranscripts.mockResolvedValue([transcript({ language: "tamil" })]);
    render(<VoiceTranscriptPanel incidentId="incident-1" />);

    expect(await screen.findByRole("region")).toHaveTextContent("heard as tamil");
  });

  it("says so, rather than implying a typed report, when the record cannot be loaded", async () => {
    listTranscripts.mockRejectedValue(new Error("offline"));
    render(<VoiceTranscriptPanel incidentId="incident-1" />);

    expect(await screen.findByText(/could not be checked just now/i)).toBeInTheDocument();
    expect(screen.queryByRole("region")).toBeNull();
  });
});
