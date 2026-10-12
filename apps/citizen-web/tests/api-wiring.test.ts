import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The bug this guards was in the wiring, not in the resolver: the app read
 * NEXT_PUBLIC_API_BASE_URL itself and quietly fell back to localhost. These tests set
 * the variable the way the build does and check what the app's own config makes of it.
 */
async function loadConfig() {
  vi.resetModules();
  return (await import("@/lib/config")).API_CONFIG;
}

describe("this app's API configuration", () => {
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is an actionable problem, not localhost, when the variable is unset", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const config = await loadConfig();
    expect(config).toMatchObject({ ok: false, problem: { code: "MISSING" } });
  });

  it("flags the deliberate .invalid placeholder", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://raksha-backend-not-deployed.invalid");
    const config = await loadConfig();
    expect(config).toMatchObject({ ok: false, problem: { code: "PLACEHOLDER" } });
  });

  it("uses the configured backend once there is one", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.acme.io");
    const config = await loadConfig();
    expect(config).toEqual({ ok: true, baseUrl: "https://api.acme.io", source: "environment" });
  });

  it("falls back to localhost in development only", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const config = await loadConfig();
    expect(config).toMatchObject({
      ok: true,
      baseUrl: "http://localhost:8000",
      source: "development-default",
    });
  });
});
