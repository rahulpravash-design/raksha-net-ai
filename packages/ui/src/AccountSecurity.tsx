"use client";

import QRCode from "qrcode";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  ApiError,
  isAuthenticatorCode,
  isSecondFactorCode,
  type MfaEnrollment,
  type User,
} from "@raksha/api-client";

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
  if (mfaEnabled && !isSecondFactorCode(values.code)) {
    errors.code = "Enter the 6-digit code from your authenticator app, or a recovery code.";
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
  /** Resolves with the recovery codes (absent from an older server). */
  mfaEnable(code: string): Promise<{ recovery_codes?: string[] }>;
  mfaRecoveryStatus(): Promise<{ remaining: number }>;
  mfaRegenerateRecoveryCodes(password: string, code: string): Promise<string[]>;
  mfaDisable(password: string, code: string): Promise<User>;
  changePassword(current: string, next: string, mfaCode?: string): Promise<unknown>;
}

const DEFAULT_PANEL = "surface space-y-4 rounded-xl p-4";
const digits = (value: string) => value.replace(/\D/g, "");
/** For a field that takes either kind of code: keep what could be one, drop the rest. */
const secondFactorText = (value: string) => value.replace(/[^A-Za-z0-9 -]/g, "").slice(0, 24);

/**
 * The second-factor field: an authenticator code or a one-time recovery code. Used by
 * the three sign-in pages and the security panels, so they cannot drift apart. The
 * field keeps `name="mfa_code"` and a plain text keyboard (a numeric one would make a
 * recovery code impossible to type).
 */
export function SecondFactorField({
  value,
  onChange,
  label = "Verification code or recovery code",
  hint = "The 6-digit code from your authenticator app. If you have lost the device, use one of your recovery codes instead — each works once.",
  error,
  required = true,
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  hint?: string;
  error?: string | undefined;
  required?: boolean;
}) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      <TextInput
        type="text"
        name="mfa_code"
        autoComplete="one-time-code"
        autoCapitalize="characters"
        autoCorrect="off"
        spellCheck={false}
        maxLength={24}
        required={required}
        value={value}
        onChange={(event) => onChange(secondFactorText(event.target.value))}
      />
    </Field>
  );
}

/**
 * Recovery codes, shown once. They cannot be fetched again, so the screen does not let
 * go of them until the person says they have kept them somewhere.
 */
export function RecoveryCodesView({
  codes,
  onDone,
  heading = "Save your recovery codes",
}: {
  codes: string[];
  onDone: () => void;
  heading?: string;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function download() {
    const blob = new Blob(
      [`RAKSHA NET AI recovery codes\nEach works once, in place of an authenticator code.\n\n${text}\n`],
      { type: "text/plain" },
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "raksha-recovery-codes.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div role="group" aria-label="Recovery codes" className="space-y-3">
      <h3 className="font-semibold">{heading}</h3>
      <p className="text-sm">
        If you lose your authenticator device, one of these signs you in. Each works{" "}
        <strong>once</strong>. Keep them somewhere safe and separate from your phone, as you
        would a password. <strong>They are not shown again.</strong>
      </p>
      <ul
        aria-label="Your recovery codes"
        className="surface grid select-all grid-cols-1 gap-1 rounded-lg px-3 py-2 font-mono text-sm sm:grid-cols-2"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={() => void copy()}>
          {copied ? "Copied" : "Copy codes"}
        </Button>
        <Button type="button" variant="secondary" onClick={download}>
          Download as a file
        </Button>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={saved}
          onChange={(event) => setSaved(event.target.checked)}
        />
        I have saved these codes somewhere safe.
      </label>
      <Button type="button" disabled={!saved} onClick={onDone}>
        Done
      </Button>
    </div>
  );
}

/**
 * Two-factor authentication for the signed-in user: enrol, confirm, recovery codes,
 * disable.
 *
 * The secret is shown only here, once per enrolment, and so are the recovery codes:
 * the server keeps only their hashes, so a lost set can be replaced but never read
 * again — and the screen holds on to them until the person says they are saved.
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
  const [renewing, setRenewing] = useState(false);
  const [issued, setIssued] = useState<{ codes: string[]; heading: string } | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const mfaOn = user.mfa_enabled;
  useEffect(() => {
    if (!mfaOn || issued) return;
    let cancelled = false;
    api
      .mfaRecoveryStatus()
      .then((status) => {
        if (!cancelled) setRemaining(status.remaining);
      })
      .catch(() => {
        // A count is a convenience; the panel works without it.
        if (!cancelled) setRemaining(null);
      });
    return () => {
      cancelled = true;
    };
  }, [api, mfaOn, issued]);

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
      if (!isAuthenticatorCode(code)) {
        throw new ApiError(400, {
          code: "VALIDATION_ERROR",
          message: "Enter the 6-digit code from your authenticator app.",
        });
      }
      const result = await api.mfaEnable(code);
      setEnrolment(null);
      setCode("");
      const codes = result?.recovery_codes ?? [];
      if (codes.length > 0) setIssued({ codes, heading: "Save your recovery codes" });
      await onChanged();
      setNotice(
        "Two-factor authentication is on. You will be asked for a code each time you sign in.",
      );
    }, "The code could not be confirmed.");

  const renew = () =>
    run(async () => {
      if (!isSecondFactorCode(code)) {
        throw new ApiError(400, {
          code: "VALIDATION_ERROR",
          message: "Enter a current authenticator code or an unused recovery code.",
        });
      }
      const codes = await api.mfaRegenerateRecoveryCodes(password, code);
      setRenewing(false);
      setPassword("");
      setCode("");
      setRemaining(codes.length);
      setIssued({ codes, heading: "Your new recovery codes" });
    }, "New recovery codes could not be made.");

  const disable = () =>
    run(async () => {
      if (!isSecondFactorCode(code)) {
        throw new ApiError(400, {
          code: "VALIDATION_ERROR",
          message: "Enter a current authenticator code or an unused recovery code.",
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
          className={`shrink-0 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
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

      {issued && (
        <RecoveryCodesView
          codes={issued.codes}
          heading={issued.heading}
          onDone={() => {
            setIssued(null);
            setNotice(null);
          }}
        />
      )}

      {!issued && !user.mfa_enabled && !enrolment && (
        <div className="space-y-2">
          <Button loading={busy} onClick={() => void begin()}>
            Set up two-factor
          </Button>
        </div>
      )}

      {!issued && enrolment && (
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
            Turning it on gives you ten one-time recovery codes to keep: they are what gets you in
            if you lose the device. Without them, an administrator has to reset your second factor —
            and an administrator cannot reset their own.
          </p>
        </div>
      )}

      {!issued && user.mfa_enabled && (
        <p
          className={`text-sm ${remaining !== null && remaining <= 3 ? "text-amber-600 dark:text-amber-200" : ""}`}
        >
          {remaining === null
            ? "Recovery codes: checking…"
            : remaining === 0
              ? "You have no recovery codes left. If you lose your device you will need an administrator — get new ones now."
              : `${remaining} unused recovery code${remaining === 1 ? "" : "s"}${remaining <= 3 ? " — running low, get new ones" : ""}.`}
        </p>
      )}

      {!issued && user.mfa_enabled && !renewing && !disabling && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setRenewing(true);
              setError(null);
              setNotice(null);
            }}
          >
            Get new recovery codes…
          </Button>
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
        </div>
      )}

      {!issued && user.mfa_enabled && renewing && (
        <div role="group" aria-label="New recovery codes" className="space-y-3">
          <p className="text-sm">
            This replaces all ten codes: any you have not used stop working. It needs your password
            and a current code.
          </p>
          <Field label="Password">
            <TextInput
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <SecondFactorField
            label="Current code or recovery code"
            hint="An authenticator code, or one recovery code you have not used."
            required={false}
            value={code}
            onChange={setCode}
          />
          <div className="flex gap-2">
            <Button loading={busy} disabled={password === ""} onClick={() => void renew()}>
              Make new codes
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setRenewing(false);
                setPassword("");
                setCode("");
                setError(null);
              }}
            >
              Keep the old ones
            </Button>
          </div>
        </div>
      )}

      {!issued && user.mfa_enabled && disabling && (
        <div role="group" aria-label="Turn off two-factor" className="space-y-3">
          <p className="text-sm">
            Turning it off needs your password and a current code — or a recovery code, if you have
            lost the device. It also deletes your recovery codes.
          </p>
          <Field label="Password">
            <TextInput
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <SecondFactorField
            label="Current code or recovery code"
            hint="An authenticator code, or one recovery code you have not used."
            required={false}
            value={code}
            onChange={setCode}
          />
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
          <SecondFactorField
            label="Code from your authenticator app, or a recovery code"
            hint="Two-factor is on, so a current code is needed too."
            error={errors.code}
            value={values.code}
            onChange={set("code")}
          />
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
