"use client";

import { ApiClient, BrowserTokenStore } from "@raksha/api-client";

import { API_BASE_URL } from "./config";

/**
 * One client and one token store per browser tab.
 *
 * A single instance matters: the client serialises refresh-token rotation
 * internally, and two instances would race each other into the backend's
 * replay detection.
 */
export const tokenStore = new BrowserTokenStore();

let client: ApiClient | null = null;

export function getApiClient(
  onUnauthenticated?: () => void,
  onMfaEnrolmentRequired?: () => void,
): ApiClient {
  if (!client) {
    client = new ApiClient({
      baseUrl: API_BASE_URL,
      tokens: tokenStore,
      ...(onUnauthenticated ? { onUnauthenticated } : {}),
      ...(onMfaEnrolmentRequired ? { onMfaEnrolmentRequired } : {}),
    });
  }
  return client;
}
