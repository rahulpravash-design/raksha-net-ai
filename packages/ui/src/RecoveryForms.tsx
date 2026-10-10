"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { ApiError } from "@raksha/api-client";

/** The slice of the API client the recovery screens need. */
export interface RecoveryApi {
  recoveryStatus(): Promise<{ email_available: boolean }>;
  requestPasswordReset(email: string): Promise<void>;
  resetPassword(token: string, newPassword: string): Promise<void>;
}

const INPUT = "surface w-full rounded-lg px-3 py-2.5 text-sm";
const PRIMARY =
  "inline-flex w-full items-center justify-center rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60";

function Alert({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg border border-red-400/60 px-4 py-3 text-sm text-red-700 dark:text-red-200">
      {children}
    </p>
  );
}

/**
 * "I forgot my password". Asks the server whether recovery by email exists at all
 * and, if it does not, says so instead of promising a message that will never
 * arrive. When it does exist the answer after submitting is the same for every
 * address — this screen must not reveal which ones have accounts.
 */
export function ForgotPasswordForm({
  api,
  signInHref,
}: {
  api: RecoveryApi;
  signInHref: string;
}) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .recoveryStatus()
      .then((status) => {
        if (!cancelled) setAvailable(status.email_available);
      })
      .catch(() => {
        // Could not ask: assume it may work and let the request itself fail visibly.
        if (!cancelled) setAvailable(true);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Enter the email address of your account.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.requestPasswordReset(email.trim());
      setSent(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Could not reach the server. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-4">
      <h1 className="text-2xl font-bold">Forgot your password?</h1>

      {available === null && <p className="text-sm opacity-70">Checking…</p>}

      {available === false && (
        <div className="space-y-3 text-sm">
          <p>
            Recovery by email is not set up for this system, so a link cannot be sent. Ask an
            administrator to set a temporary password for you.
          </p>
          <a href={signInHref} className="font-semibold underline">
            Back to sign in
          </a>
        </div>
      )}

      {available === true && !sent && (
        <form onSubmit={(event) => void submit(event)} noValidate className="space-y-4">
          <p className="text-sm opacity-80">
            Enter the email address of your account and we will send a link to choose a new
            password.
          </p>
          {error && <Alert>{error}</Alert>}
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">Email address</span>
            <input
              type="email"
              name="email"
              autoComplete="email"
              className={INPUT}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <button type="submit" disabled={busy} className={PRIMARY}>
            {busy ? "Sending…" : "Send the link"}
          </button>
          <a href={signInHref} className="block text-center text-sm underline">
            Back to sign in
          </a>
        </form>
      )}

      {available === true && sent && (
        <div role="status" className="space-y-3 text-sm">
          <p className="font-semibold">Check your email.</p>
          <p>
            If an account exists for that address, a link to choose a new password is on its way.
            It works once and expires soon. Nothing here confirms whether the address has an
            account.
          </p>
          <a href={signInHref} className="font-semibold underline">
            Back to sign in
          </a>
        </div>
      )}
    </div>
  );
}

/** Choose a new password from a recovery link. Does not sign you in. */
export function ResetPasswordForm({
  api,
  token,
  signInHref,
  forgotHref,
}: {
  api: RecoveryApi;
  token: string | null;
  signInHref: string;
  forgotHref: string;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linkDead, setLinkDead] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (password === "") {
      setError("Choose a new password.");
      return;
    }
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "INVALID_RESET_TOKEN") setLinkDead(true);
      setError(
        caught instanceof ApiError ? caught.message : "Could not reach the server. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!token || linkDead) {
    return (
      <div className="mx-auto max-w-sm space-y-3">
        <h1 className="text-2xl font-bold">Link not valid</h1>
        <p className="text-sm">
          {!token
            ? "This page needs the link from your recovery email."
            : "This recovery link is invalid or has expired. Links work once and expire soon."}
        </p>
        <a href={forgotHref} className="font-semibold underline">
          Request a new link
        </a>
      </div>
    );
  }

  if (done) {
    return (
      <div role="status" className="mx-auto max-w-sm space-y-3">
        <h1 className="text-2xl font-bold">Password changed</h1>
        <p className="text-sm">
          Your password has been changed and every other session was signed out. Sign in with the
          new password.
        </p>
        <a href={signInHref} className={PRIMARY}>
          Sign in
        </a>
      </div>
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="mx-auto max-w-sm space-y-4">
      <h1 className="text-2xl font-bold">Choose a new password</h1>
      {error && <Alert>{error}</Alert>}
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">New password</span>
        <input type="password" autoComplete="new-password" className={INPUT} value={password} onChange={(e) => setPassword(e.target.value)} />
        <span className="mt-1 block text-xs opacity-70">
          Use a long passphrase you do not use anywhere else. The server rejects passwords that
          are too short or too common.
        </span>
      </label>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Repeat the new password</span>
        <input type="password" autoComplete="new-password" className={INPUT} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </label>
      <button type="submit" disabled={busy} className={PRIMARY}>
        {busy ? "Saving…" : "Change password"}
      </button>
      <p className="text-xs opacity-70">
        If you use an authenticator app, you will still be asked for a code when you sign in.
      </p>
    </form>
  );
}
