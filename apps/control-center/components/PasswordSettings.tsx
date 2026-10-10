"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import { validatePasswordChange, type PasswordFormErrors } from "@/lib/password";
import { homeFor } from "@/lib/routes";

const EMPTY = { current: "", next: "", confirm: "", code: "" };

/**
 * Change your own password. Needs the current one (and a current authenticator
 * code when two-factor is on). On success every other session of this account is
 * ended and this one carries on with fresh tokens.
 */
export function PasswordSettings() {
  const api = getApiClient();
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const [values, setValues] = useState(EMPTY);
  const [errors, setErrors] = useState<PasswordFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!user) return null;
  const forced = user.must_change_password;

  const set = (key: keyof typeof values) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;
    const found = validatePasswordChange(values, user.mfa_enabled);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    setServerError(null);
    setNotice(null);
    try {
      await api.changePassword(values.current, values.next, user.mfa_enabled ? values.code : undefined);
      setValues(EMPTY);
      await refreshUser();
      if (forced) {
        router.replace(homeFor(user.role));
        return;
      }
      setNotice("Password changed. Your other sessions have been signed out.");
    } catch (caught) {
      setServerError(caught instanceof ApiError ? caught.message : "The password could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Password" className="panel-3d space-y-4 rounded-xl p-4">
      <div>
        <h2 className="text-lg font-bold">Password</h2>
        <p className="muted text-sm">
          Use a long passphrase you do not use anywhere else. Changing it signs this account out
          of every other device.
        </p>
      </div>

      {forced && (
        <p role="note" className="rounded-lg border border-amber-300/60 px-3 py-2 text-sm text-amber-200">
          An administrator set your password, so it is known to them. Choose your own now — nothing
          else in the console will work until you do.
        </p>
      )}

      <ErrorBanner message={serverError} />
      {notice && (
        <p role="status" className="text-sm text-[var(--accent)]">
          {notice}
        </p>
      )}

      <form onSubmit={(event) => void submit(event)} noValidate className="space-y-3">
        <Field label="Current password" required error={errors.current}>
          <TextInput type="password" autoComplete="current-password" value={values.current} onChange={(e) => set("current")(e.target.value)} />
        </Field>
        <Field label="New password" required error={errors.next} hint="The server applies its own minimum length and rejects common passwords.">
          <TextInput type="password" autoComplete="new-password" value={values.next} onChange={(e) => set("next")(e.target.value)} />
        </Field>
        <Field label="Repeat the new password" required error={errors.confirm}>
          <TextInput type="password" autoComplete="new-password" value={values.confirm} onChange={(e) => set("confirm")(e.target.value)} />
        </Field>
        {user.mfa_enabled && (
          <Field label="Code from your authenticator app" required error={errors.code} hint="Two-factor is on, so a current code is needed too.">
            <TextInput inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={values.code} onChange={(e) => set("code")(e.target.value.replace(/\D/g, ""))} />
          </Field>
        )}
        <Button type="submit" loading={busy}>
          Change password
        </Button>
      </form>
      <p className="muted text-xs">
        Five wrong attempts lock the account for a while, exactly as at sign-in. If you have
        forgotten your password, an administrator can set a temporary one.
      </p>
    </section>
  );
}
