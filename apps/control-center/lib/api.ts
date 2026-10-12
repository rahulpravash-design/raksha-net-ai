"use client";

import {
  ApiClient,
  BrowserTokenStore,
  apiConnection,
  resolveApiConfig,
} from "@raksha/api-client";

import { API_CONFIG } from "./config";

/**
 * One client and one token store per browser tab.
 *
 * A single instance matters: the client serialises refresh-token rotation
 * internally, and two instances would race each other into the backend's
 * replay detection.
 */
export const tokenStore = new BrowserTokenStore();

let client: ApiClient | null = null;

/**
 * The build-time config, checked once more in the browser: an API at `localhost` cannot
 * work for a visitor on any other host, and only the browser knows which host that is.
 */
function connectionConfig() {
  if (!API_CONFIG.ok || typeof window === "undefined") return API_CONFIG;
  return resolveApiConfig({
    value: API_CONFIG.baseUrl,
    production: process.env.NODE_ENV === "production",
    pageOrigin: window.location.origin,
  });
}

export function getApiClient(
  onUnauthenticated?: () => void,
  onMfaEnrolmentRequired?: () => void,
  onPasswordChangeRequired?: () => void,
): ApiClient {
  if (!client) {
    client = new ApiClient({
      ...apiConnection(connectionConfig()),
      tokens: tokenStore,
      ...(onUnauthenticated ? { onUnauthenticated } : {}),
      ...(onMfaEnrolmentRequired ? { onMfaEnrolmentRequired } : {}),
      ...(onPasswordChangeRequired ? { onPasswordChangeRequired } : {}),
    });
  }
  return client;
}
