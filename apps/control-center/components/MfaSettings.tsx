"use client";

import { useState } from "react";

import { ApiError, type MfaEnrollment } from "@raksha/api-client";

import { QrCode } from "@/components/QrCode";
import { useAuth } from "@/components/AuthProvider";
import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

/** "JBSWY3DPEHPK3PXP" -> "JBSW Y3DP EHPK 3PXP", easier to read and type. */
export function groupSecret(secret: string): string {
  return secret.replace(/\s+/g, "").replace(/(.{4})/g, "$1 ").trim();
}

const CODE = /^\d{6}$/;

/**
 * Two-factor authentication for the signed-in user: enrol, confirm, disable.
 *
 * The secret is shown only here, once per enrolment. There are no recovery
 * codes: a user who loses the device must have an administrator reset it, and
 * the screen says so before they rely on it.
 */
export function MfaSettings() {
  const api = getApiClient();
  const { user, refreshUser } = useAuth();
  const [enrolment, setEnrolment] = useState<MfaEnrollment | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [disabling, setDisabling] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!user) return null;

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  const begin = () =>
    run(async () => {
      setEnrolment(await api.mfaEnroll());
      setCode("");
    }, "Setup could not be started.");

  const confirm = () =>
    run(async () => {
      if (!CODE.test(code)) throw new ApiError(400, { code: "VALIDATION_ERROR", message: "Enter the 6-digit code from your authenticator app." });
      await api.mfaEnable(code);
      setEnrolment(null);
      setCode("");
      await refreshUser();
      setNotice("Two-factor authentication is on. You will be asked for a code each time you sign in.");
    }, "The code could not be confirmed.");

  const disable = () =>
    run(async () => {
      if (!CODE.test(code)) throw new ApiError(400, { code: "VALIDATION_ERROR", message: "Enter the current 6-digit code." });
      await api.mfaDisable(password, code);
      setDisabling(false);
      setPassword("");
      setCode("");
      await refreshUser();
      setNotice("Two-factor authentication is off.");
    }, "Two-factor authentication could not be turned off.");

  return (
    <section aria-label="Two-factor authentication" className="panel-3d space-y-4 rounded-xl p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">Two-factor authentication</h2>
          <p className="muted text-sm">
            A code from an authenticator app, asked for after your password, protects this account
            if the password is stolen.
          </p>
        </div>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
            user.mfa_enabled ? "border-[var(--accent)]/50 text-[var(--accent)]" : "border-amber-300/60 text-amber-200"
          }`}
        >
          {user.mfa_enabled ? "● On" : "○ Off"}
        </span>
      </div>

      <ErrorBanner message={error} />
      {notice && (
        <p role="status" className="text-sm text-[var(--accent)]">
          {notice}
        </p>
      )}

      {!user.mfa_enabled && !enrolment && (
        <div className="space-y-2">
          <Button loading={busy} onClick={() => void begin()}>
            Set up two-factor
          </Button>
        </div>
      )}

      {enrolment && (
        <div className="space-y-3">
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            <li>Open an authenticator app (any TOTP app works).</li>
            <li>Scan this code, or enter the key by hand.</li>
            <li>Type the 6-digit code it shows, below.</li>
          </ol>
          <div className="flex flex-wrap items-center gap-4">
            <QrCode value={enrolment.provisioning_uri} label="QR code for your authenticator app" />
            <div className="space-y-1 text-sm">
              <p className="muted">Or enter this key:</p>
              <p className="surface select-all rounded-lg px-3 py-2 font-mono" aria-label="Setup key">
                {groupSecret(enrolment.secret)}
              </p>
              <p className="muted text-xs">Time-based, 6 digits. Shown only now — do not share it.</p>
            </div>
          </div>
          <Field label="Code from the app" hint="Six digits.">
            <TextInput inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </Field>
          <div className="flex gap-2">
            <Button loading={busy} onClick={() => void confirm()}>
              Turn on
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => { setEnrolment(null); setCode(""); setError(null); }}>
              Cancel
            </Button>
          </div>
          <p className="muted text-xs">
            There are no backup codes. If you lose the device, an administrator has to reset your
            second factor before you can sign in again — and an administrator cannot reset their own.
          </p>
        </div>
      )}

      {user.mfa_enabled && !disabling && (
        <Button variant="danger" onClick={() => { setDisabling(true); setError(null); setNotice(null); }}>
          Turn off two-factor…
        </Button>
      )}

      {user.mfa_enabled && disabling && (
        <div role="group" aria-label="Turn off two-factor" className="space-y-3">
          <p className="text-sm">Turning it off needs your password and a current code.</p>
          <Field label="Password">
            <TextInput type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Current code">
            <TextInput inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </Field>
          <div className="flex gap-2">
            <Button variant="danger" loading={busy} disabled={password === ""} onClick={() => void disable()}>
              Confirm turn off
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => { setDisabling(false); setPassword(""); setCode(""); setError(null); }}>
              Keep it on
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
