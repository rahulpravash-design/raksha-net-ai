import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { VoiceTranscript } from "@raksha/api-client";

import ReportPage from "@/app/report/page";

const push = vi.fn();
const createIncident = vi.fn();
const uploadMedia = vi.fn();
const transcriptionAvailability = vi.fn();
const transcribe = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", role: "CITIZEN" }, loading: false }),
}));
vi.mock("@/lib/api", () => ({
  getApiClient: () => ({
    createIncident,
    uploadMedia,
    transcriptionAvailability,
    transcribe,
  }),
}));
// Location capture is tested on its own; here it only has to supply a position.
vi.mock("@/components/LocationField", () => ({
  EMPTY_LOCATION: { latitude: null, longitude: null, accuracyMetres: null, source: null },
  LocationField: ({
    onChange,
  }: {
    onChange: (value: {
      latitude: number;
      longitude: number;
      accuracyMetres: number;
      source: "manual";
    }) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onChange({ latitude: 13.08, longitude: 80.27, accuracyMetres: 10, source: "manual" })
      }
    >
      Set test location
    </button>
  ),
}));

const HEARD = "Five people are trapped and the water is rising.";

const TRANSCRIPT: VoiceTranscript = {
  id: "11111111-1111-4111-8111-111111111111",
  incident_id: null,
  source: "AI_TRANSCRIPT",
  text: HEARD,
  confidence: 0.88,
  language: "english",
  language_hint: null,
  duration_seconds: 4,
  model_name: "whisper-1",
  model_version: "1.0.0",
  provider: "openai",
  reporter_edited: null,
  created_at: "2026-01-01T09:00:00Z",
};

class FakeRecorder {
  static isTypeSupported = () => true;
  mimeType: string;
  state: "inactive" | "recording" = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(_stream: unknown, options: { mimeType: string }) {
    this.mimeType = options.mimeType;
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function dictationAvailable() {
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
    },
  });
}

async function dictate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /record a voice report/i }));
  await user.click(screen.getByRole("button", { name: /stop and add/i }));
  await screen.findByText(/added to your description by speech recognition/i);
}

beforeEach(() => {
  push.mockReset();
  uploadMedia.mockReset();
  createIncident.mockReset().mockResolvedValue({ id: "incident-1" });
  transcribe.mockReset().mockResolvedValue(TRANSCRIPT);
  transcriptionAvailability.mockReset().mockResolvedValue({
    available: true,
    max_bytes: 8 * 1024 * 1024,
    accepted_types: ["audio/webm", "audio/ogg", "audio/mp4"],
    languages: ["en", "ta"],
  });
  vi.unstubAllGlobals();
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
});

describe("the report form with dictation", () => {
  it("puts the transcript in the description for the reporter to read, and sends its id", async () => {
    dictationAvailable();
    render(<ReportPage />);
    const user = userEvent.setup();

    await dictate(user);
    const description = screen.getByLabelText(/describe the situation/i);
    expect(description).toHaveValue(HEARD);

    await user.click(screen.getByRole("button", { name: /set test location/i }));
    await user.click(screen.getByRole("button", { name: /submit report/i }));

    await waitFor(() => expect(createIncident).toHaveBeenCalled());
    expect(createIncident.mock.calls[0]![0]).toMatchObject({
      description: HEARD,
      transcript_id: TRANSCRIPT.id,
    });
  });

  it("sends the reporter's corrections, not the model's words", async () => {
    dictationAvailable();
    render(<ReportPage />);
    const user = userEvent.setup();

    await dictate(user);
    const description = screen.getByLabelText(/describe the situation/i);
    await user.clear(description);
    await user.type(description, "Six people are trapped and the water is rising.");
    await user.click(screen.getByRole("button", { name: /set test location/i }));
    await user.click(screen.getByRole("button", { name: /submit report/i }));

    await waitFor(() => expect(createIncident).toHaveBeenCalled());
    expect(createIncident.mock.calls[0]![0]).toMatchObject({
      description: "Six people are trapped and the water is rising.",
      transcript_id: TRANSCRIPT.id,
    });
  });

  it("adds to what the reporter had already typed instead of replacing it", async () => {
    dictationAvailable();
    render(<ReportPage />);
    const user = userEvent.setup();

    await user.type(
      await screen.findByLabelText(/describe the situation/i),
      "Corner of Gandhi Road.",
    );
    await dictate(user);

    expect(screen.getByLabelText(/describe the situation/i)).toHaveValue(
      `Corner of Gandhi Road.\n${HEARD}`,
    );
  });

  it("files a typed report with no transcript id when nothing was dictated", async () => {
    dictationAvailable();
    render(<ReportPage />);
    const user = userEvent.setup();

    await user.type(
      await screen.findByLabelText(/describe the situation/i),
      "Fire on the second floor, people inside.",
    );
    await user.click(screen.getByRole("button", { name: /set test location/i }));
    await user.click(screen.getByRole("button", { name: /submit report/i }));

    await waitFor(() => expect(createIncident).toHaveBeenCalled());
    expect(createIncident.mock.calls[0]![0].transcript_id).toBeNull();
    expect(transcribe).not.toHaveBeenCalled();
  });

  it("refuses a description that dictation pushed past the limit, rather than cutting it off", async () => {
    dictationAvailable();
    transcribe.mockResolvedValue({ ...TRANSCRIPT, text: "x".repeat(4100) });
    render(<ReportPage />);
    const user = userEvent.setup();

    await dictate(user);
    await user.click(screen.getByRole("button", { name: /set test location/i }));
    await user.click(screen.getByRole("button", { name: /submit report/i }));

    expect(await screen.findByText(/too long/i)).toBeInTheDocument();
    expect(createIncident).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/describe the situation/i)).toHaveValue("x".repeat(4100));
  });

  it("is a plain typing form when the service offers no dictation", async () => {
    dictationAvailable();
    transcriptionAvailability.mockResolvedValue({
      available: false,
      max_bytes: 0,
      accepted_types: [],
      languages: [],
    });
    render(<ReportPage />);
    const user = userEvent.setup();

    await waitFor(() => expect(transcriptionAvailability).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /record a voice report/i })).toBeNull();

    await user.type(
      screen.getByLabelText(/describe the situation/i),
      "Road collapsed near the bridge, vehicle trapped.",
    );
    await user.click(screen.getByRole("button", { name: /set test location/i }));
    await user.click(screen.getByRole("button", { name: /submit report/i }));
    await waitFor(() => expect(createIncident).toHaveBeenCalled());
  });
});
