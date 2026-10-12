/**
 * Validation of the API address a front end was built with.
 *
 * `NEXT_PUBLIC_API_BASE_URL` is compiled into the bundle, so a wrong value does not
 * fail loudly: the browser's `fetch` just rejects, and every screen used to say "Could
 * not reach the server". This module turns the commonest misconfigurations into a named
 * problem with an instruction, so an operator is told what to fix instead of a visitor
 * being told to check their connection.
 *
 * There is deliberately no production fallback. A development build with the variable
 * unset uses `http://localhost:8000` (the address `docker compose` and the README use);
 * a production build with it unset has no API and says so.
 *
 * Pure and free of I/O: the caller reads `process.env.NEXT_PUBLIC_API_BASE_URL` itself
 * (Next.js only inlines that exact expression) and passes the value in.
 */

/** The variable every front end reads, named in messages so the fix is findable. */
export const API_URL_VARIABLE = "NEXT_PUBLIC_API_BASE_URL";

/** What an unconfigured *development* build talks to. Never used in production. */
export const DEVELOPMENT_API_URL = "http://localhost:8000";

export type ApiConfigProblemCode =
  | "MISSING"
  | "NOT_A_URL"
  | "NOT_HTTP"
  | "HAS_CREDENTIALS"
  | "PLACEHOLDER"
  | "INSECURE_IN_PRODUCTION"
  | "LOOPBACK_FROM_REMOTE_PAGE";

export interface ApiConfigProblem {
  code: ApiConfigProblemCode;
  /** Safe to show to anyone: says what is wrong and what the site owner must do. */
  message: string;
}

export type ApiConfig =
  | { ok: true; baseUrl: string; source: "environment" | "development-default" }
  | { ok: false; problem: ApiConfigProblem };

export interface ApiConfigInput {
  /** The raw `process.env.NEXT_PUBLIC_API_BASE_URL`, undefined when unset. */
  value: string | undefined;
  /** True for a production build (`NODE_ENV === "production"`). */
  production: boolean;
  /** The origin the page is served from, when known (browser only). */
  pageOrigin?: string | undefined;
}

const NOT_CONNECTED = "This site is not connected to its RAKSHA NET AI server.";
const OWNER_ACTION = `The site owner must set ${API_URL_VARIABLE} to the backend's https:// address and redeploy.`;

const MESSAGES: Record<ApiConfigProblemCode, string> = {
  MISSING: `${NOT_CONNECTED} ${API_URL_VARIABLE} is not set. ${OWNER_ACTION}`,
  NOT_A_URL: `${NOT_CONNECTED} ${API_URL_VARIABLE} is not a valid URL. ${OWNER_ACTION}`,
  NOT_HTTP: `${NOT_CONNECTED} ${API_URL_VARIABLE} must start with https:// (or http:// for local development). ${OWNER_ACTION}`,
  HAS_CREDENTIALS: `${NOT_CONNECTED} ${API_URL_VARIABLE} contains a username or password. That value is public, so it must be a plain address. ${OWNER_ACTION}`,
  PLACEHOLDER: `${NOT_CONNECTED} ${API_URL_VARIABLE} still holds a placeholder address because no backend has been deployed or linked yet. ${OWNER_ACTION}`,
  INSECURE_IN_PRODUCTION: `${NOT_CONNECTED} ${API_URL_VARIABLE} uses plain http://, which browsers block from an https:// site and which would expose credentials. ${OWNER_ACTION}`,
  LOOPBACK_FROM_REMOTE_PAGE: `${NOT_CONNECTED} ${API_URL_VARIABLE} points at localhost, which for a visitor is their own device. ${OWNER_ACTION}`,
};

function problem(code: ApiConfigProblemCode): ApiConfig {
  return { ok: false, problem: { code, message: MESSAGES[code] } };
}

/** `localhost`, `127.x.x.x`, `::1` and `*.localhost`. */
export function isLoopbackHost(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  return (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host === "::1" ||
    /^127(\.\d{1,3}){3}$/.test(host)
  );
}

/**
 * Hosts that can never be a real backend. `.invalid` is reserved by RFC 2606 to never
 * resolve and is what an undeployed backend's placeholder uses; in a production build
 * the documentation names (`.example`, `example.com|net|org`) are placeholders too.
 */
function isPlaceholderHost(hostname: string, production: boolean): boolean {
  const host = hostname.toLowerCase();
  if (host === "invalid" || host.endsWith(".invalid")) return true;
  if (!production) return false;
  return (
    host === "example" ||
    host.endsWith(".example") ||
    /(^|\.)example\.(com|net|org)$/.test(host)
  );
}

export function resolveApiConfig({
  value,
  production,
  pageOrigin,
}: ApiConfigInput): ApiConfig {
  const raw = value?.trim() ?? "";
  if (raw === "") {
    if (production) return problem("MISSING");
    return { ok: true, baseUrl: DEVELOPMENT_API_URL, source: "development-default" };
  }

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return problem("NOT_A_URL");
  }

  if (url.protocol !== "https:" && url.protocol !== "http:") return problem("NOT_HTTP");
  if (url.username !== "" || url.password !== "") return problem("HAS_CREDENTIALS");
  if (isPlaceholderHost(url.hostname, production)) return problem("PLACEHOLDER");

  const loopback = isLoopbackHost(url.hostname);
  if (production && url.protocol === "http:" && !loopback) {
    return problem("INSECURE_IN_PRODUCTION");
  }

  if (loopback && pageOrigin) {
    let pageHost: string | null = null;
    try {
      pageHost = new URL(pageOrigin).hostname;
    } catch {
      // An unparseable page origin proves nothing; do not guess a problem from it.
    }
    if (pageHost !== null && !isLoopbackHost(pageHost)) {
      return problem("LOOPBACK_FROM_REMOTE_PAGE");
    }
  }

  return { ok: true, baseUrl: url.href.replace(/\/+$/, ""), source: "environment" };
}

/** The `ApiClient` options that follow from a resolved config. */
export type ApiConnection =
  | { baseUrl: string }
  | { baseUrl: string; configProblem: ApiConfigProblem };

/**
 * An unusable config still needs *some* `baseUrl` to construct the client; the client
 * refuses every request before using it (see `ApiConfigurationError`).
 */
export function apiConnection(config: ApiConfig): ApiConnection {
  return config.ok
    ? { baseUrl: config.baseUrl }
    : { baseUrl: "", configProblem: config.problem };
}
