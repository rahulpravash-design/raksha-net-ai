"use client";

import { useSyncExternalStore } from "react";

/**
 * Whether a CSS media query currently matches. `serverValue` is what server
 * rendering (and the first hydration pass) assumes; the real answer follows
 * straight after. Where `matchMedia` is missing it reports `false`.
 */
export function useMediaQuery(query: string, serverValue: boolean): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = typeof window.matchMedia === "function" ? window.matchMedia(query) : null;
      list?.addEventListener("change", notify);
      return () => list?.removeEventListener("change", notify);
    },
    () => (typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false),
    () => serverValue,
  );
}
