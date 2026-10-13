import { describe, expect, it } from "vitest";

import {
  MAX_RECORDING_SECONDS,
  formatElapsed,
  microphoneMessage,
  pickRecordingType,
} from "@/lib/recording";

const SERVER_ACCEPTS = ["audio/webm", "audio/ogg", "audio/mp4"];

describe("pickRecordingType", () => {
  it("prefers opus in WebM where the browser can record it", () => {
    expect(pickRecordingType(() => true, SERVER_ACCEPTS)).toBe(
      "audio/webm;codecs=opus",
    );
  });

  it("falls back through what the browser supports", () => {
    expect(pickRecordingType((t) => t === "audio/webm", SERVER_ACCEPTS)).toBe(
      "audio/webm",
    );
    expect(
      pickRecordingType((t) => t.startsWith("audio/ogg"), SERVER_ACCEPTS),
    ).toBe("audio/ogg;codecs=opus");
  });

  it("gives Safari the one format it can record", () => {
    expect(pickRecordingType((t) => t === "audio/mp4", SERVER_ACCEPTS)).toBe(
      "audio/mp4",
    );
  });

  it("offers nothing the server would refuse", () => {
    expect(pickRecordingType(() => true, ["audio/ogg"])).toBe(
      "audio/ogg;codecs=opus",
    );
    expect(pickRecordingType(() => true, [])).toBeNull();
  });

  it("offers nothing when the browser supports none of them", () => {
    expect(pickRecordingType(() => false, SERVER_ACCEPTS)).toBeNull();
  });
});

describe("formatElapsed", () => {
  it.each([
    [0, "0:00"],
    [7.9, "0:07"],
    [65, "1:05"],
    [MAX_RECORDING_SECONDS, "2:00"],
    [-3, "0:00"],
  ])("renders %d seconds as %s", (seconds, expected) => {
    expect(formatElapsed(seconds)).toBe(expected);
  });
});

describe("microphoneMessage", () => {
  it.each([
    "NotAllowedError",
    "NotFoundError",
    "NotReadableError",
    "AbortError",
  ])("%s still tells the reporter they can type", (name) => {
    expect(microphoneMessage({ name })).toMatch(/type your report/i);
  });

  it("tells a refusal apart from a missing microphone", () => {
    expect(microphoneMessage({ name: "NotAllowedError" })).toMatch(
      /permission/i,
    );
    expect(microphoneMessage({ name: "NotFoundError" })).toMatch(
      /no microphone/i,
    );
  });

  it("copes with a value that is not an error", () => {
    expect(microphoneMessage(null)).toMatch(/type your report/i);
    expect(microphoneMessage("nope")).toMatch(/type your report/i);
  });
});
