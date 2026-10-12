"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

import {
  bandStyle,
  statusLabel,
  type IncidentStatus,
  type PriorityBand,
} from "@raksha/api-client";

export function Button({
  variant = "primary",
  loading = false,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
  loading?: boolean;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60";
  const variants = {
    primary: "bg-brand-600 text-white hover:bg-brand-700",
    secondary:
      "surface hover:bg-slate-50 dark:hover:bg-slate-800 text-[var(--foreground)]",
    danger: "bg-red-600 text-white hover:bg-red-700",
  } as const;

  return (
    <button
      className={`${base} ${variants[variant]} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | undefined;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">
        {label}
        {required && (
          <span aria-hidden="true" className="ml-1 text-red-600">
            *
          </span>
        )}
      </span>
      {children}
      {hint && !error && <span className="muted mt-1 block text-xs">{hint}</span>}
      {error && (
        <span role="alert" className="mt-1 block text-xs font-medium text-red-600">
          {error}
        </span>
      )}
    </label>
  );
}

export function TextInput({
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`surface w-full rounded-lg px-3 py-2.5 text-sm ${className}`}
      {...rest}
    />
  );
}

/**
 * The error surface every page uses.
 *
 * `role="alert"` so a screen reader announces a failed submission without the
 * user having to hunt for what went wrong.
 */
export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200"
    >
      {message}
    </div>
  );
}

/**
 * Priority badge.
 *
 * Carries its own text label, so the band survives greyscale and colour-blind
 * viewing — colour is a second signal, never the only one.
 */
export function PriorityBadge({ band }: { band: PriorityBand | null }) {
  const style = bandStyle(band);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide ${style.badge}`}
    >
      {style.label}
    </span>
  );
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const terminal = ["CLOSED", "CANCELLED", "DUPLICATE", "REJECTED"].includes(status);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        terminal
          ? "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200"
          : "bg-brand-100 text-brand-900 dark:bg-brand-900 dark:text-brand-100"
      }`}
    >
      {statusLabel(status)}
    </span>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-8 text-sm muted" role="status">
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent"
      />
      {label}…
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="surface rounded-xl px-6 py-12 text-center">
      <p className="font-semibold">{title}</p>
      <p className="muted mx-auto mt-2 max-w-md text-sm">{body}</p>
    </div>
  );
}
