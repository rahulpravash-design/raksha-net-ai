import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError, type TokenStore } from "@raksha/api-client";

class MemoryTokenStore implements TokenStore {
  access: string | null = "access-1";
  refresh: string | null = "refresh-1";

  getAccessToken() {
    return this.access;
  }
  getRefreshToken() {
    return this.refresh;
  }
  setTokens(tokens: { access: string; refresh: string }) {
    this.access = tokens.access;
    this.refresh = tokens.refresh;
  }
  clear() {
    this.access = null;
    this.refresh = null;
  }
}

/** A fetch mock that carries fetch's own argument types. */
type FetchArgs = [input: RequestInfo | URL, init?: RequestInit];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ApiError", () => {
  it("exposes the backend error code and message", () => {
    const error = new ApiError(409, {
      code: "EMAIL_ALREADY_REGISTERED",
      message: "An account with this email address already exists.",
    });
    expect(error.code).toBe("EMAIL_ALREADY_REGISTERED");
    expect(error.message).toContain("already exists");
  });

  it("flattens field errors for form display", () => {
    const error = new ApiError(400, {
      code: "VALIDATION_ERROR",
      details: {
        fields: [
          { field: "email", message: "value is not a valid email address" },
          { field: "description", message: "too short" },
        ],
      },
    });
    expect(error.fieldErrors).toEqual({
      email: "value is not a valid email address",
      description: "too short",
    });
  });

  it("returns no field errors when details carry none", () => {
    expect(new ApiError(500).fieldErrors).toEqual({});
  });

  it("marks throttling and server faults as retryable, not client mistakes", () => {
    expect(new ApiError(429).isRetryable).toBe(true);
    expect(new ApiError(503).isRetryable).toBe(true);
    expect(new ApiError(400).isRetryable).toBe(false);
    expect(new ApiError(403).isRetryable).toBe(false);
  });
});

describe("ApiClient", () => {
  let tokens: MemoryTokenStore;

  beforeEach(() => {
    tokens = new MemoryTokenStore();
  });

  it("sends the access token as a bearer credential", async () => {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) =>
      jsonResponse({ id: "u1" }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await client.me();

    const [, init] = fetchImpl.mock.calls[0]!;
    expect((init as RequestInit).headers).toMatchObject({
      Authorization: "Bearer access-1",
    });
  });

  it("turns an error envelope into an ApiError", async () => {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) =>
      jsonResponse(
        { error: { code: "NOT_FOUND", message: "Incident not found." } },
        404,
      ),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(client.incident("abc")).rejects.toMatchObject({
      status: 404,
      code: "NOT_FOUND",
    });
  });

  it("still raises an ApiError when the failure is not JSON", async () => {
    const fetchImpl = vi.fn(
      async (..._args: FetchArgs) =>
        new Response("<html>gateway error</html>", { status: 502 }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(client.health()).rejects.toBeInstanceOf(ApiError);
  });

  it("refreshes once on a 401 and replays the original request", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: "TOKEN_EXPIRED" } }, 401),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "access-2",
          refresh_token: "refresh-2",
          token_type: "bearer",
          expires_in: 1800,
          user: { id: "u1" },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ id: "u1" }));

    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(client.me()).resolves.toMatchObject({ id: "u1" });
    expect(tokens.access).toBe("access-2");
    expect(tokens.refresh).toBe("refresh-2");
  });

  it("rotates the refresh token only once for concurrent 401s", async () => {
    // Two parallel requests presenting the same refresh token would look like
    // credential replay to the backend and end every session, so the client
    // must serialise the rotation.
    const fetchImpl = vi.fn(async (...args: FetchArgs) => {
      const url = String(args[0]);
      if (url.endsWith("/auth/refresh")) {
        return jsonResponse({
          access_token: "access-2",
          refresh_token: "refresh-2",
          token_type: "bearer",
          expires_in: 1800,
          user: { id: "u1" },
        });
      }
      return tokens.access === "access-1"
        ? jsonResponse({ error: { code: "TOKEN_EXPIRED" } }, 401)
        : jsonResponse({ id: "u1" });
    });

    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await Promise.all([client.me(), client.me(), client.me()]);

    const refreshCalls = fetchImpl.mock.calls.filter((call) =>
      String(call[0]).endsWith("/auth/refresh"),
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it("clears the session and notifies when the refresh is rejected", async () => {
    const onUnauthenticated = vi.fn();
    const fetchImpl = vi.fn(async (...args: FetchArgs) =>
      String(args[0]).endsWith("/auth/refresh")
        ? jsonResponse({ error: { code: "INVALID_TOKEN" } }, 401)
        : jsonResponse({ error: { code: "TOKEN_EXPIRED" } }, 401),
    );

    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      onUnauthenticated,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(client.me()).rejects.toBeInstanceOf(ApiError);
    expect(tokens.access).toBeNull();
    expect(onUnauthenticated).toHaveBeenCalledOnce();
  });

  it("does not attempt a refresh for the login endpoint itself", async () => {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) =>
      jsonResponse({ error: { code: "INVALID_CREDENTIALS" } }, 401),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(client.login("a@example.org", "wrong")).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it("sends a verification code with the login only when one is supplied", async () => {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) =>
      jsonResponse({ error: { code: "MFA_REQUIRED" } }, 401),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(client.login("a@example.org", "pw")).rejects.toMatchObject({
      code: "MFA_REQUIRED",
    });
    await expect(
      client.login("a@example.org", "pw", "123456"),
    ).rejects.toBeInstanceOf(ApiError);

    const [without, withCode] = fetchImpl.mock.calls.map(
      (call) => JSON.parse(String((call[1] as RequestInit).body)) as object,
    );
    expect(without).toEqual({ email: "a@example.org", password: "pw" });
    expect(withCode).toEqual({
      email: "a@example.org",
      password: "pw",
      mfa_code: "123456",
    });
  });

  it("serialises repeatable query parameters for multi-value filters", async () => {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) =>
      jsonResponse({ items: [], total: 0 }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await client.incidentQueue({ status: ["REPORTED", "RECEIVED"], page: 2 });

    const url = String(fetchImpl.mock.calls[0]![0]);
    expect(url).toContain("status=REPORTED");
    expect(url).toContain("status=RECEIVED");
    expect(url).toContain("page=2");
  });

  it("omits empty filters instead of sending blank values", async () => {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) =>
      jsonResponse({ items: [], total: 0 }),
    );
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await client.incidentQueue({ q: "" });

    expect(String(fetchImpl.mock.calls[0]![0])).not.toContain("q=");
  });

  it("signs out locally even when the server call fails", async () => {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) => {
      throw new Error("network down");
    });
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await client.logout();
    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
  });
});

describe("ApiClient voice reports", () => {
  let tokens: MemoryTokenStore;
  beforeEach(() => {
    tokens = new MemoryTokenStore();
  });

  function clientWith(response: () => Response) {
    const fetchImpl = vi.fn(async (..._args: FetchArgs) => response());
    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokens,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    return { client, fetchImpl };
  }

  it("sends the recording as a multipart file, with the language only when chosen", async () => {
    const { client, fetchImpl } = clientWith(() => jsonResponse({ id: "t1" }, 201));
    const recording = new Blob(["audio-bytes"], { type: "audio/webm;codecs=opus" });

    await client.transcribe(recording, "ta");
    await client.transcribe(recording);

    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(String(url)).toBe("http://api.test/api/v1/transcriptions");
    expect((init as RequestInit).method).toBe("POST");
    const withLanguage = (init as RequestInit).body as FormData;
    expect(withLanguage.get("language")).toBe("ta");
    expect((withLanguage.get("file") as File).size).toBe("audio-bytes".length);
    // The browser sets the multipart boundary; a JSON content type would break it.
    expect((init as RequestInit).headers).not.toHaveProperty("Content-Type");

    const withoutLanguage = (fetchImpl.mock.calls[1]![1] as RequestInit).body as FormData;
    expect(withoutLanguage.has("language")).toBe(false);
  });

  it("reads availability and an incident's transcripts from their own endpoints", async () => {
    const { client, fetchImpl } = clientWith(() => jsonResponse([]));

    await client.transcriptionAvailability();
    await client.listTranscripts("inc-9");

    expect(String(fetchImpl.mock.calls[0]![0])).toBe(
      "http://api.test/api/v1/transcriptions/availability",
    );
    expect(String(fetchImpl.mock.calls[1]![0])).toBe(
      "http://api.test/api/v1/incidents/inc-9/transcripts",
    );
  });

  it("raises the server's own message when transcription is unavailable", async () => {
    const { client } = clientWith(() =>
      jsonResponse(
        {
          error: {
            code: "TRANSCRIPTION_UNAVAILABLE",
            message: "Voice reports are not available right now. Please type your report.",
          },
        },
        503,
      ),
    );

    await expect(client.transcribe(new Blob(["x"]))).rejects.toMatchObject({
      status: 503,
      code: "TRANSCRIPTION_UNAVAILABLE",
      message: expect.stringContaining("type your report"),
    });
  });
});
