import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** NEXT_PUBLIC_ values are read where they are written, so test them the way the build sets them. */
async function loadCitizenUrl() {
  vi.resetModules();
  return (await import("@/lib/config")).CITIZEN_APP_URL;
}

describe("the citizen app address", () => {
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is not guessed in production: unset and blank both mean 'not linked'", async () => {
    vi.stubEnv("NEXT_PUBLIC_CITIZEN_APP_URL", "");
    expect(await loadCitizenUrl()).toBeUndefined();
    vi.stubEnv("NEXT_PUBLIC_CITIZEN_APP_URL", "   ");
    expect(await loadCitizenUrl()).toBeUndefined();
  });

  it("uses the configured address", async () => {
    vi.stubEnv("NEXT_PUBLIC_CITIZEN_APP_URL", "https://raksha-citizen.netlify.app");
    expect(await loadCitizenUrl()).toBe("https://raksha-citizen.netlify.app");
  });

  it("guesses localhost in development only", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_CITIZEN_APP_URL", "");
    expect(await loadCitizenUrl()).toBe("http://localhost:3000");
  });
});
