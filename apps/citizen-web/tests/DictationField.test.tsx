import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type VoiceTranscript } from "@raksha/api-client";

import { DictationField } from "@/components/DictationField";

const transcriptionAvailability = vi.fn();
const transcribe = vi.fn();

vi.mock("@/lib/api", () => ({
  getApiClient: () => ({ transcriptionAvailability, transcribe }),
}));

const AVAILABLE = {
  available: true,
  max_bytes: 1024,
  accepted_types: ["audio/webm", "audio/ogg", "audio/mp4"],
  languages: ["en", "ta"],
};

function transcript(overrides: Partial<VoiceTranscript> = {}): VoiceTranscript {
  return {
    id: "transcript-1",
    incident_id: null,
    source: "AI_TRANSCRIPT",
    text: "Water is rising in the lane.",
    confidence: 0.9,
    language: "english",
    language_hint: null,
    duration_seconds: 3,
    model_name: "whisper-1",
    model_version: "1.0.0",
    provider: "openai",
    reporter_edited: null,
    created_at: "2026-01-01T09:00:00Z",
    ...overrides,
  };
}

/** A recorder that "records" one chunk of the size a test chooses. */
let chunkBytes = 8;
const trackStop = vi.fn();

class FakeRecorder {
  static isTypeSupported = (type: string) => type.startsWith("audio/webm");
  mimeType: string;
  state: "inactive" | "recording" = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(
    public stream: unknown,
    options: { mimeType: string },
  ) {
    this.mimeType = options.mimeType;
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({
      data: new Blob([new Uint8Array(chunkBytes)], { type: this.mimeType }),
    });
    this.onstop?.();
  }
}

function installBrowserRecording(
  getUserMedia = vi
    .fn()
    .mockResolvedValue({ getTracks: () => [{ stop: trackStop }] }),
) {
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });
  return getUserMedia;
}

async function openField(
  props: Partial<Parameters<typeof DictationField>[0]> = {},
) {
  const onTranscript = vi.fn();
  render(<DictationField onTranscript={onTranscript} {...props} />);
  return { onTranscript };
}

const RECORD = /record a voice report/i;

beforeEach(() => {
  chunkBytes = 8;
  trackStop.mockReset();
  transcriptionAvailability.mockReset().mockResolvedValue(AVAILABLE);
  transcribe.mockReset().mockResolvedValue(transcript());
});
afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: undefined,
  });
});

describe("DictationField is only ever an extra", () => {
  it("renders nothing when the service does not offer dictation", async () => {
    installBrowserRecording();
    transcriptionAvailability.mockResolvedValue({
      ...AVAILABLE,
      available: false,
    });
    const { container } = render(<DictationField onTranscript={vi.fn()} />);

    await waitFor(() => expect(transcriptionAvailability).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the availability check fails", async () => {
    installBrowserRecording();
    transcriptionAvailability.mockRejectedValue(new Error("network"));
    const { container } = render(<DictationField onTranscript={vi.fn()} />);

    await waitFor(() => expect(transcriptionAvailability).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing, and asks the server nothing, in a browser that cannot record", async () => {
    // No MediaRecorder and no microphone API: jsdom's defaults.
    const { container } = render(<DictationField onTranscript={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
    expect(transcriptionAvailability).not.toHaveBeenCalled();
  });

  it("renders nothing when the browser records only a format the server refuses", async () => {
    installBrowserRecording();
    transcriptionAvailability.mockResolvedValue({
      ...AVAILABLE,
      accepted_types: ["audio/wav"],
    });
    const { container } = render(<DictationField onTranscript={vi.fn()} />);

    await waitFor(() => expect(transcriptionAvailability).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("dictating a report", () => {
  it("records, sends the recording, hands over the transcript and releases the microphone", async () => {
    const getUserMedia = installBrowserRecording();
    const { onTranscript } = await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(screen.getByRole("status")).toHaveTextContent(/recording/i);

    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    await waitFor(() =>
      expect(onTranscript).toHaveBeenCalledWith(transcript()),
    );
    const [blob, language] = transcribe.mock.calls[0]!;
    expect((blob as Blob).size).toBe(8);
    expect((blob as Blob).type).toBe("audio/webm;codecs=opus");
    expect(language).toBeNull();
    expect(trackStop).toHaveBeenCalled();
  });

  it("says plainly that speech recognition can be wrong and the reporter must check it", async () => {
    installBrowserRecording();
    await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    const notice = await screen.findByText(
      /added to your description by speech recognition/i,
    );
    expect(notice).toHaveTextContent(/90% confidence/);
    expect(notice).toHaveTextContent(/read it and correct anything/i);
    expect(notice).not.toHaveTextContent(/not sure of these words/i);
  });

  it("warns when the recogniser was unsure", async () => {
    installBrowserRecording();
    transcribe.mockResolvedValue(transcript({ confidence: 0.4 }));
    await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    expect(
      await screen.findByText(/not sure of these words/i),
    ).toBeInTheDocument();
  });

  it("passes the language the reporter chose", async () => {
    installBrowserRecording();
    await openField();
    const user = userEvent.setup();

    await user.selectOptions(
      await screen.findByLabelText(/language spoken/i),
      "ta",
    );
    await user.click(screen.getByRole("button", { name: RECORD }));
    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    await waitFor(() => expect(transcribe).toHaveBeenCalled());
    expect(transcribe.mock.calls[0]![1]).toBe("ta");
  });

  it("states what happens to the recording before anything is recorded", async () => {
    installBrowserRecording();
    await openField();

    expect(
      await screen.findByText(/we do not keep the recording/i),
    ).toHaveTextContent(/sent to a speech-recognition service/i);
  });
});

describe("when dictation does not work, typing still does", () => {
  it("explains a refused microphone and sends nothing", async () => {
    installBrowserRecording(
      vi.fn().mockRejectedValue({ name: "NotAllowedError" }),
    );
    await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /permission was refused/i,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/type your report/i);
    expect(transcribe).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: RECORD })).toBeEnabled();
  });

  it("shows the server's own words when transcription is unavailable", async () => {
    installBrowserRecording();
    transcribe.mockRejectedValue(
      new ApiError(503, {
        code: "TRANSCRIPTION_UNAVAILABLE",
        message:
          "Voice reports are not available right now. Please type your report.",
      }),
    );
    const { onTranscript } = await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /please type your report/i,
    );
    expect(onTranscript).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: RECORD })).toBeEnabled();
  });

  it("falls back to a plain message when the request itself fails", async () => {
    installBrowserRecording();
    transcribe.mockRejectedValue(new TypeError("Failed to fetch"));
    await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /type your report instead/i,
    );
  });

  it("does not send an empty recording", async () => {
    installBrowserRecording();
    chunkBytes = 0;
    await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /nothing was recorded/i,
    );
    expect(transcribe).not.toHaveBeenCalled();
  });

  it("does not send a recording larger than the server accepts", async () => {
    installBrowserRecording();
    chunkBytes = AVAILABLE.max_bytes + 1;
    await openField();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    await user.click(screen.getByRole("button", { name: /stop and add/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/too long/i);
    expect(transcribe).not.toHaveBeenCalled();
  });

  it("abandons a recording in progress when the form goes away, sending nothing", async () => {
    installBrowserRecording();
    const { unmount } = render(<DictationField onTranscript={vi.fn()} />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: RECORD }));
    unmount();

    expect(trackStop).toHaveBeenCalled();
    expect(transcribe).not.toHaveBeenCalled();
  });

  it("cannot be started while the report is being sent", async () => {
    installBrowserRecording();
    await openField({ disabled: true });

    expect(await screen.findByRole("button", { name: RECORD })).toBeDisabled();
  });
});
