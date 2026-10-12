import { describe, expect, it, vi } from "vitest";

import {
  ApiClient,
  ApiConfigurationError,
  ApiError,
  apiConnection,
  isLoopbackHost,
  resolveApiConfig,
  type ApiConfig,
} from "@raksha/api-client";

/** A fetch mock that carries fetch's own argument types. */
type FetchArgs = [input: RequestInfo | URL, init?: RequestInit];

const production = { production: true } as const;
const development = { production: false } as const;

function problemCode(config: ApiConfig): string | null {
  return config.ok ? null : config.problem.code;
}

describe("resolveApiConfig", () => {
  it("accepts a real https address and strips the trailing slash", () => {
    const config = resolveApiConfig({
      ...production,
      value: "https://raksha-api.onrender.com/",
    });
    expect(config).toEqual({
      ok: true,
      baseUrl: "https://raksha-api.onrender.com",
      source: "environment",
    });
  });

  it("keeps a path prefix, for a backend served under one", () => {
    const config = resolveApiConfig({ ...production, value: "https://api.acme.io/raksha/" });
    expect(config).toMatchObject({ ok: true, baseUrl: "https://api.acme.io/raksha" });
  });

  it("has no fallback in production: unset, empty and blank are all MISSING", () => {
    for (const value of [undefined, "", "   "]) {
      expect(problemCode(resolveApiConfig({ ...production, value }))).toBe("MISSING");
    }
  });

  it("falls back to localhost only in development, and says that it did", () => {
    expect(resolveApiConfig({ ...development, value: undefined })).toEqual({
      ok: true,
      baseUrl: "http://localhost:8000",
      source: "development-default",
    });
  });

  it("rejects the .invalid placeholder in every build", () => {
    const placeholder = "https://raksha-backend-not-deployed.invalid";
    expect(problemCode(resolveApiConfig({ ...production, value: placeholder }))).toBe(
      "PLACEHOLDER",
    );
    expect(problemCode(resolveApiConfig({ ...development, value: placeholder }))).toBe(
      "PLACEHOLDER",
    );
  });

  it("treats documentation names as placeholders in production only", () => {
    for (const value of ["https://api.example.com", "https://x.example", "https://example.org"]) {
      expect(problemCode(resolveApiConfig({ ...production, value }))).toBe("PLACEHOLDER");
      expect(resolveApiConfig({ ...development, value }).ok).toBe(true);
    }
  });

  it("rejects values that are not a URL or not http(s)", () => {
    expect(problemCode(resolveApiConfig({ ...production, value: "not a url" }))).toBe(
      "NOT_A_URL",
    );
    expect(problemCode(resolveApiConfig({ ...production, value: "api.acme.io" }))).toBe(
      "NOT_A_URL",
    );
    expect(problemCode(resolveApiConfig({ ...production, value: "ftp://api.acme.io" }))).toBe(
      "NOT_HTTP",
    );
  });

  it("rejects an address with embedded credentials — NEXT_PUBLIC_ values are public", () => {
    const config = resolveApiConfig({
      ...production,
      value: "https://admin:hunter2@api.acme.io",
    });
    expect(problemCode(config)).toBe("HAS_CREDENTIALS");
    // The message must not repeat the secret it is complaining about.
    expect(JSON.stringify(config)).not.toContain("hunter2");
  });

  it("requires https in production but allows plain http to loopback", () => {
    expect(problemCode(resolveApiConfig({ ...production, value: "http://api.acme.io" }))).toBe(
      "INSECURE_IN_PRODUCTION",
    );
    // A local `docker compose` stack is a production build talking to localhost.
    expect(resolveApiConfig({ ...production, value: "http://localhost:8000" }).ok).toBe(true);
    expect(resolveApiConfig({ ...development, value: "http://api.acme.io" }).ok).toBe(true);
  });

  it("rejects localhost when the page is served from anywhere else", () => {
    const value = "http://localhost:8000";
    expect(
      problemCode(
        resolveApiConfig({ ...production, value, pageOrigin: "https://raksha-citizen.netlify.app" }),
      ),
    ).toBe("LOOPBACK_FROM_REMOTE_PAGE");
    expect(
      resolveApiConfig({ ...production, value, pageOrigin: "http://localhost:3000" }).ok,
    ).toBe(true);
    expect(
      resolveApiConfig({ ...production, value, pageOrigin: "http://127.0.0.1:3000" }).ok,
    ).toBe(true);
  });

  it("gives every problem a message that names the variable and the remedy", () => {
    const messages = [
      resolveApiConfig({ ...production, value: undefined }),
      resolveApiConfig({ ...production, value: "x" }),
      resolveApiConfig({ ...production, value: "https://a.invalid" }),
      resolveApiConfig({ ...production, value: "http://a.io" }),
    ].map((config) => (config.ok ? "" : config.problem.message));
    for (const message of messages) {
      expect(message).toContain("NEXT_PUBLIC_API_BASE_URL");
      expect(message).toContain("redeploy");
    }
  });
});

describe("isLoopbackHost", () => {
  it("recognises the loopback spellings and nothing near them", () => {
    for (const host of ["localhost", "app.localhost", "127.0.0.1", "127.1.2.3", "[::1]", "::1"]) {
      expect(isLoopbackHost(host)).toBe(true);
    }
    for (const host of ["localhost.evil.io", "127.0.0.1.evil.io", "10.0.0.1", "api.acme.io"]) {
      expect(isLoopbackHost(host)).toBe(false);
    }
  });
});

describe("a client built from an unusable config", () => {
  const unusable = resolveApiConfig({ ...production, value: undefined });

  it("refuses every request before touching the network", async () => {
    const fetchImpl = vi.fn();
    const client = new ApiClient({
      ...apiConnection(unusable),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(
      client.register({ email: "a@example.org", password: "x", full_name: "A B" }),
    ).rejects.toBeInstanceOf(ApiConfigurationError);
    await expect(client.login("a@example.org", "x")).rejects.toBeInstanceOf(
      ApiConfigurationError,
    );
    await expect(client.health()).rejects.toBeInstanceOf(ApiConfigurationError);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("is an ApiError, so every screen shows its message rather than a generic one", async () => {
    const client = new ApiClient({ ...apiConnection(unusable) });
    const error = await client.health().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 0,
      code: "API_NOT_CONFIGURED",
      details: { reason: "MISSING" },
    });
    expect((error as ApiError).message).toContain("NEXT_PUBLIC_API_BASE_URL");
    expect((error as ApiError).isRetryable).toBe(false);
  });

  it("does not stop a client with a usable config from working", async () => {
    const fetchImpl = vi.fn(
      async (..._args: FetchArgs) =>
        new Response(JSON.stringify({ status: "ok", version: "1" })),
    );
    const client = new ApiClient({
      ...apiConnection(resolveApiConfig({ ...production, value: "https://api.acme.io" })),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(client.health()).resolves.toMatchObject({ status: "ok" });
    expect(String(fetchImpl.mock.calls[0]![0])).toBe("https://api.acme.io/api/v1/health");
  });
});
