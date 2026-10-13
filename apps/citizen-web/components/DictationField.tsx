"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  confidenceTier,
  formatConfidence,
  type SpeechLanguage,
  type TranscriptionAvailability,
  type VoiceTranscript,
} from "@raksha/api-client";

import { getApiClient } from "@/lib/api";
import {
  MAX_RECORDING_SECONDS,
  canRecord,
  formatElapsed,
  microphoneMessage,
  pickRecordingType,
} from "@/lib/recording";
import { Button } from "./ui";

type Status = "idle" | "recording" | "transcribing";

const LANGUAGE_OPTIONS: { value: SpeechLanguage | ""; label: string }[] = [
  { value: "", label: "Detect automatically" },
  { value: "en", label: "English" },
  { value: "ta", label: "Tamil" },
];

/**
 * Dictate the description instead of typing it.
 *
 * Rule 7 (CLAUDE.md section 2): this only ever sits beside the typing box. It renders
 * nothing unless the service offers dictation AND this browser can record, and any
 * failure leaves the reporter where they started, with the box they can already type in.
 *
 * What comes back is an AI transcript, not the report: the caller puts it in the
 * description for the reporter to read and correct, and this component says so.
 */
export function DictationField({
  onTranscript,
  disabled,
}: {
  onTranscript: (transcript: VoiceTranscript) => void;
  disabled?: boolean;
}) {
  const [offer, setOffer] = useState<{
    availability: TranscriptionAvailability;
    mimeType: string;
  } | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [language, setLanguage] = useState<SpeechLanguage | "">("");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<VoiceTranscript | null>(null);

  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  /** Set when a recording is abandoned (unmount): it must not be sent. */
  const discard = useRef(false);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      if (!canRecord()) return;
      try {
        const availability = await getApiClient().transcriptionAvailability();
        if (cancelled || !availability.available) return;
        const mimeType = pickRecordingType(
          (type) => MediaRecorder.isTypeSupported(type),
          availability.accepted_types,
        );
        if (mimeType) setOffer({ availability, mimeType });
      } catch {
        // Not offered. The report form works without it.
      }
    }
    void check();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(
    () => () => {
      discard.current = true;
      if (timer.current) clearInterval(timer.current);
      if (recorder.current?.state === "recording") recorder.current.stop();
      stream.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  if (!offer) return null;
  const { availability, mimeType } = offer;

  function release() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  async function transcribe(recording: Blob) {
    if (recording.size === 0) {
      setError("Nothing was recorded. Try again, or type your report.");
      setStatus("idle");
      return;
    }
    if (recording.size > availability.max_bytes) {
      setError(
        "That recording is too long to send. Record a shorter message, or type it.",
      );
      setStatus("idle");
      return;
    }
    setStatus("transcribing");
    try {
      const transcript = await getApiClient().transcribe(
        recording,
        language || null,
      );
      setLast(transcript);
      onTranscript(transcript);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The recording could not be sent. Please type your report instead.",
      );
    } finally {
      setStatus("idle");
    }
  }

  async function start() {
    setError(null);
    setLast(null);
    discard.current = false;
    let microphone: MediaStream;
    try {
      microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (caught) {
      setError(microphoneMessage(caught));
      return;
    }
    stream.current = microphone;
    chunks.current = [];

    const active = new MediaRecorder(microphone, { mimeType });
    active.ondataavailable = (event: BlobEvent) => {
      if (event.data.size > 0) chunks.current.push(event.data);
    };
    active.onstop = () => {
      release();
      if (discard.current) return;
      void transcribe(
        new Blob(chunks.current, { type: active.mimeType || mimeType }),
      );
    };
    recorder.current = active;
    active.start();
    setElapsed(0);
    setStatus("recording");

    const startedAt = Date.now();
    timer.current = setInterval(() => {
      const seconds = (Date.now() - startedAt) / 1000;
      setElapsed(seconds);
      if (seconds >= MAX_RECORDING_SECONDS && active.state === "recording")
        active.stop();
    }, 500);
  }

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  return (
    <div className="surface space-y-3 rounded-xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">Prefer to speak?</p>
        <label className="flex items-center gap-2 text-sm">
          <span className="muted">Language spoken</span>
          <select
            aria-label="Language spoken"
            className="surface rounded-lg px-2 py-1.5 text-sm"
            value={language}
            disabled={disabled || status !== "idle"}
            onChange={(event) =>
              setLanguage(event.target.value as SpeechLanguage | "")
            }
          >
            {LANGUAGE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {status === "idle" && (
        <Button
          type="button"
          variant="secondary"
          disabled={disabled}
          onClick={() => void start()}
        >
          Record a voice report
        </Button>
      )}
      {status === "recording" && (
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="danger" onClick={stop}>
            Stop and add to description
          </Button>
          <span aria-hidden="true" className="text-sm tabular-nums">
            {formatElapsed(elapsed)} / {formatElapsed(MAX_RECORDING_SECONDS)}
          </span>
        </div>
      )}

      <p role="status" className="text-sm">
        {status === "recording" &&
          "Recording. Press stop when you have finished."}
        {status === "transcribing" && "Turning your recording into text…"}
      </p>

      {error && (
        <p role="alert" className="text-sm font-medium text-red-600">
          {error}
        </p>
      )}

      {last && status === "idle" && !error && (
        <p
          role="status"
          className="rounded-lg bg-violet-50 px-3 py-2 text-sm dark:bg-violet-950"
        >
          Added to your description by speech recognition (
          {formatConfidence(last.confidence)}).{" "}
          {confidenceTier(last.confidence) === "low" && (
            <strong>It was not sure of these words. </strong>
          )}
          It can get words wrong: read it and correct anything before you send
          your report.
        </p>
      )}

      <p className="muted text-xs">
        We do not keep the recording. It is sent to a speech-recognition service
        to be turned into text, and only the text is saved with your report.
      </p>
    </div>
  );
}
