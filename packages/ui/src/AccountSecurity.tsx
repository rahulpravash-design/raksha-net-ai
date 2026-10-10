"use client";

import QRCode from "qrcode";
import { useMemo, useState, type FormEvent } from "react";

import { ApiError, type MfaEnrollment, type User } from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "./primitives";

// --- password form rules -------------------------------------------------------

export interface PasswordFormValues {
  current: string;
  next: string;
  confirm: string;
  code: string;
}

export type PasswordFormErrors = Partial<Record<keyof PasswordFormValues, string>>;

/**
 * Checks that catch typing mistakes before a round trip. The server's password
 * rules (minimum length, common passwords) are configuration, so the client does
 * not restate them: it shows the server's own message when they are not met.
 */
export function validatePasswordChange(
  values: PasswordFormValues,
  mfaEnabled: boolean,
): PasswordFormErrors {
  const errors: PasswordFormErrors = {};
  if (values.current === "") errors.current = "Enter your current password.";
  if (values.next === "") errors.next = "Choose a new password.";
  else if (values.next === values.current) {
    errors.next = "The new password must be different from the current one.";
  }
  if (values.next !== "" && values.confirm !== values.next) {
    errors.confirm = "The two new passwords do not match.";
  }
  if (mfaEnabled && !/^\d{6}$/.test(values.code)) {
    errors.code = "Enter the 6-digit code from your authenticator app.";
  }
  return errors;
}

// --- QR code ---------------------------------------------------------------------

const QUIET_ZONE = 4;

/**
 * A QR code drawn as one SVG path. Built from the library's module matrix rather
 * than injected markup, so nothing here parses a string as HTML. Always dark on
 * white with the standard 4-module quiet zone — authenticator apps will not read
 * a themed or inverted code.
 */
export function QrCode({ value, label }: { value: string; label: string }) {
  const { size, path } = useMemo(() => {
    const qr = QRCode.create(value, { errorCorrectionLevel: "M" });
    const count = qr.modules.size;
    let d = "";
    for (let row = 0; row < count; row++) {
      for (let col = 0; col < count; col++) {
        if (qr.modules.get(row, col)) d += `M${col + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`;
      }
    }
    return { size: count + QUIET_ZONE * 2, path: d };
  }, [value]);

  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${size} ${size}`}
      shapeRendering="crispEdges"
      className="h-48 w-48 rounded-lg bg-white"
    >
      <path d={path} fill="#000" />
    </svg>
  );
}

/** "JBSWY3DPEHPK3PXP" -> "JBSW Y3DP EHPK 3PXP", easier to read and type. */
export function groupSecret(secret: string): string {
  return secret.replace(/\s+/g, "").replace(/(.{4})/g, "$1 ").trim();
}

// --- panels ------------------------------------------------------------------------

/** The slice of the API client the account-security panels need. */
export interface SecurityApi {
  mfaEnroll(): Promise<MfaEnrollment>;
  mfaEnable(code: string): Promise<User>;
  mfaDisable(password: string, code: string): Promise<User>;
  changePassword(current: string, next: string, mfaCode?: string): Promise<unknown>;
}

const DEFAULT_PANEL = "surface space-y-4 rounded-xl p-4";
const CODE = /^\d{6}$/;
const digits = (value: string) => value.replace(/\D/g, "");

/**
 * Two-factor authentication for the signed-in user: enrol, confirm, disable.
 *
 * The secret is shown only here, once per enrolment. There are no recovery
 * codes: a user who loses the device must have an administrator reset it, and
 * the screen says so before they rely on it.
 */
export function MfaPanel({
  api,
  user,
  onChanged,
  className = DEFAULT_PANEL,
}: {
  api: SecurityApi;
  user: User;
  /** Called after the account's two-factor state changed, to reload the user. */
  onChanged: () => Promise<void> | void;
  className?: string;
}) {
  const [enrolment, setEnrolment] = useState<MfaEnrollment | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [disabling, setDisabling] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
      if (!CODE.test(code)) {
        throw new ApiError(400, {
          code: "VALIDATION_ERROR",
          message: "Enter the 6-digit code from your authenticator app.",
        });
      }
      await api.mfaEnable(code);
      setEnrolment(null);
      setCode("");
      await onChanged();
      setNotice(
        "Two-factor authentication is on. You will be asked for a code each time you sign in.",
      );
    }, "The code could not be confirmed.");

  const disable = () =>
    run(async () => {
      if (!CODE.test(code)) {
        throw new ApiError(400, {
          code: "VALIDATION_ERROR",
          message: "Enter the current 6-digit code.",
        });
      }
      await api.mfaDisable(password, code);
      setDisabling(false);
      setPassword("");
      setCode("");
      await onChanged();
      setNotice("Two-factor authentication is off.");
    }, "Two-factor authentication could not be turned off.");

  return (
    <section aria-label="Two-factor authentication" className={className}>
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
            user.mfa_enabled
              ? "border-emerald-500/50 text-emerald-600 dark:text-emerald-300"
              : "border-amber-400/60 text-amber-600 dark:text-amber-200"
          }`}
        >
          {user.mfa_enabled ? "● On" : "○ Off"}
        </span>
      </div>

      <ErrorBanner message={error} />
      {notice && (
        <p role="status" className="text-sm text-emerald-600 dark:text-emerald-300">
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
              <p
                className="surface select-all rounded-lg px-3 py-2 font-mono"
                aria-label="Setup key"
              >
                {groupSecret(enrolment.secret)}
              </p>
              <p className="muted text-xs">
                Time-based, 6 digits. Shown only now — do not share it.
              </p>
            </div>
          </div>
          <Field label="Code from the app" hint="Six digits.">
            <TextInput
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(digits(e.target.value))}
            />
          </Field>
          <div className="flex gap-2">
            <Button loading={busy} onClick={() => void confirm()}>
              Turn on
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setEnrolment(null);
                setCode("");
                setError(null);
              }}
            >
              Cancel
            </Button>
          </div>
          <p className="muted text-xs">
            There are no backup codes. If you lose the device, an administrator has to reset your
            second factor before you can sign in again — and an administrator cannot reset their
            own.
          </p>
        </div>
      )}

      {user.mfa_enabled && !disabling && (
        <Button
          variant="danger"
          onClick={() => {
            setDisabling(true);
            setError(null);
            setNotice(null);
          }}
        >
          Turn off two-factor…
        </Button>
      )}

      {user.mfa_enabled && disabling && (
        <div role="group" aria-label="Turn off two-factor" className="space-y-3">
          <p className="text-sm">Turning it off needs your password and a current code.</p>
          <Field label="Password">
            <TextInput
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Field label="Current code">
            <TextInput
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(digits(e.target.value))}
            />
          </Field>
          <div className="flex gap-2">
            <Button
              variant="danger"
              loading={busy}
              disabled={password === ""}
              onClick={() => void disable()}
            >
              Confirm turn off
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setDisabling(false);
                setPassword("");
                setCode("");
                setError(null);
              }}
            >
              Keep it on
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

const EMPTY = { current: "", next: "", confirm: "", code: "" };

/**
 * Change your own password. Needs the current one (and a current authenticator
 * code when two-factor is on). On success every other session of this account is
 * ended and this one carries on with fresh tokens.
 */
export function PasswordPanel({
  api,
  user,
  onChanged,
  onForcedChangeDone,
  className = DEFAULT_PANEL,
}: {
  api: SecurityApi;
  user: User;
  onChanged: () => Promise<void> | void;
  /** After an administrator-set password has been replaced: where to go next. */
  onForcedChangeDone: () => void;
  className?: string;
}) {
  const [values, setValues] = useState(EMPTY);
  const [errors, setErrors] = useState<PasswordFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const forced = user.must_change_password;
  const set = (key: keyof typeof values) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = validatePasswordChange(values, user.mfa_enabled);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    setServerError(null);
    setNotice(null);
    try {
      await api.changePassword(
        values.current,
        values.next,
        user.mfa_enabled ? values.code : undefined,
      );
      setValues(EMPTY);
      await onChanged();
      if (forced) {
        onForcedChangeDone();
        return;
      }
      setNotice("Password changed. Your other sessions have been signed out.");
    } catch (caught) {
      setServerError(
        caught instanceof ApiError ? caught.message : "The password could not be changed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Password" className={className}>
      <div>
        <h2 className="text-lg font-bold">Password</h2>
        <p className="muted text-sm">
          Use a long passphrase you do not use anywhere else. Changing it signs this account out of
          every other device.
        </p>
      </div>

      {forced && (
        <p
          role="note"
          className="rounded-lg border border-amber-400/60 px-3 py-2 text-sm text-amber-700 dark:text-amber-200"
        >
          An administrator set your password, so it is known to them. Choose your own now — nothing
          else will work until you do.
        </p>
      )}

      <ErrorBanner message={serverError} />
      {notice && (
        <p role="status" className="text-sm text-emerald-600 dark:text-emerald-300">
          {notice}
        </p>
      )}

      <form onSubmit={(event) => void submit(event)} noValidate className="space-y-3">
        <Field label="Current password" required error={errors.current}>
          <TextInput
            type="password"
            autoComplete="current-password"
            value={values.current}
            onChange={(e) => set("current")(e.target.value)}
          />
        </Field>
        <Field
          label="New password"
          required
          error={errors.next}
          hint="The server applies its own minimum length and rejects common passwords."
        >
          <TextInput
            type="password"
            autoComplete="new-password"
            value={values.next}
            onChange={(e) => set("next")(e.target.value)}
          />
        </Field>
        <Field label="Repeat the new password" required error={errors.confirm}>
          <TextInput
            type="password"
            autoComplete="new-password"
            value={values.confirm}
            onChange={(e) => set("confirm")(e.target.value)}
          />
        </Field>
        {user.mfa_enabled && (
          <Field
            label="Code from your authenticator app"
            required
            error={errors.code}
            hint="Two-factor is on, so a current code is needed too."
          >
            <TextInput
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={values.code}
              onChange={(e) => set("code")(digits(e.target.value))}
            />
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
