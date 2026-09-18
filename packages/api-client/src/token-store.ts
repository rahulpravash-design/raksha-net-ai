/**
 * Browser token storage.
 *
 * `sessionStorage` rather than `localStorage`: an operator's console token
 * should not outlive the browser session on a shared workstation. This is a
 * deliberate trade of convenience for a smaller theft window — see
 * `docs/SECURITY.md` section 2.
 *
 * The stronger option is an httpOnly cookie, which needs the backend to set it
 * and a CSRF strategy to go with it. That is recorded in the roadmap rather
 * than half-built here.
 */

import type { TokenStore } from "./client";

const ACCESS_KEY = "raksha.access_token";
const REFRESH_KEY = "raksha.refresh_token";

/** Used during server rendering, where no browser storage exists. */
export class NullTokenStore implements TokenStore {
  getAccessToken(): string | null {
    return null;
  }
  getRefreshToken(): string | null {
    return null;
  }
  setTokens(): void {}
  clear(): void {}
}

export class BrowserTokenStore implements TokenStore {
  private listeners = new Set<() => void>();

  private get storage(): Storage | null {
    if (typeof window === "undefined") return null;
    try {
      return window.sessionStorage;
    } catch {
      // Storage can throw outright when site data is blocked.
      return null;
    }
  }

  getAccessToken(): string | null {
    try {
      return this.storage?.getItem(ACCESS_KEY) ?? null;
    } catch {
      return null;
    }
  }

  getRefreshToken(): string | null {
    try {
      return this.storage?.getItem(REFRESH_KEY) ?? null;
    } catch {
      return null;
    }
  }

  setTokens(tokens: { access: string; refresh: string }): void {
    try {
      this.storage?.setItem(ACCESS_KEY, tokens.access);
      this.storage?.setItem(REFRESH_KEY, tokens.refresh);
    } catch {
      // A session that cannot persist still works until the page is reloaded.
    }
    this.notify();
  }

  clear(): void {
    try {
      this.storage?.removeItem(ACCESS_KEY);
      this.storage?.removeItem(REFRESH_KEY);
    } catch {
      // Nothing to clear.
    }
    this.notify();
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) listener();
  }
}
