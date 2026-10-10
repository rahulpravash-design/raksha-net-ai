"use client";

import { ForgotPasswordForm } from "@raksha/ui";

import { getApiClient } from "@/lib/api";

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm api={getApiClient()} signInHref="/login" />;
}
