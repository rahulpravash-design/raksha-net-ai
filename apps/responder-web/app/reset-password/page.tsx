"use client";

import { useEffect, useState } from "react";

import { ResetPasswordForm } from "@raksha/ui";

import { getApiClient } from "@/lib/api";

/**
 * Reads the recovery token from the link and then removes it from the address
 * bar, so it does not linger in history or get copied along with the URL.
 */
export default function ResetPasswordPage() {
  const [token, setToken] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setToken(params.get("token"));
    if (params.has("token")) window.history.replaceState(null, "", window.location.pathname);
  }, []);

  if (token === undefined) return null;
  return (
    <ResetPasswordForm
      api={getApiClient()}
      token={token}
      signInHref="/login"
      forgotHref="/forgot-password"
    />
  );
}
