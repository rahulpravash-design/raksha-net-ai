/**
 * Helpers for recording a voice report in the browser (Phase 9).
 *
 * Kept free of React so each decision is testable on its own.
 */

/** Longest dictation. Two minutes of speech is far below the server's size cap. */
export const MAX_RECORDING_SECONDS = 120;

/**
 * The types `MediaRecorder` records into, best first. Chrome, Edge and Firefox offer WebM,
 * Firefox also Ogg, and Safari only MP4: the server accepts exactly these three.
 */
const RECORDING_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
] as const;

/**
 * The first recording type this browser supports and the server accepts, or null when
 * dictation is not possible here (the form then offers typing only).
 */
export function pickRecordingType(
  isSupported: (type: string) => boolean,
  accepted: readonly string[],
): string | null {
  return (
    RECORDING_TYPES.find(
      (type) => isSupported(type) && accepted.includes(type.split(";")[0]!),
    ) ?? null
  );
}

/** 0:07, 1:05 */
export function formatElapsed(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** Whether this browser can record at all. */
export function canRecord(): boolean {
  return (
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function" &&
    typeof MediaRecorder !== "undefined"
  );
}

/**
 * What to tell the reporter when the microphone could not be opened. Every message ends
 * the same way: typing is always available.
 */
export function microphoneMessage(error: unknown): string {
  const name = (error as { name?: string } | null)?.name;
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone permission was refused. You can type your report instead.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No microphone was found on this device. You can type your report instead.";
    case "NotReadableError":
      return "The microphone is in use by another app. Close it and try again, or type your report.";
    default:
      return "The microphone could not be opened. You can type your report instead.";
  }
}
