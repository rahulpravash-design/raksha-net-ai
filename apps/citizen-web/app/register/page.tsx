"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ApiError } from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";

/** Mirrors the backend policy so the user is told before they submit. */
const MIN_PASSWORD_LENGTH = 12;

export default function RegisterPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const api = getApiClient();

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    phone: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  function update(key: keyof typeof form, value: string) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    if (form.password.length < MIN_PASSWORD_LENGTH) {
      setFieldErrors({
        password: `Use at least ${MIN_PASSWORD_LENGTH} characters. A short phrase you will remember works well.`,
      });
      return;
    }

    setSubmitting(true);
    try {
      await api.register({
        email: form.email,
        password: form.password,
        full_name: form.full_name,
        phone: form.phone.trim() === "" ? null : form.phone,
      });
      // Signing in straight away means one less step during an emergency.
      await signIn(form.email, form.password);
      router.push("/report");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFieldErrors(caught.fieldErrors);
      } else {
        setError("Could not reach the server. Please check your connection.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-bold">Create an account</h1>
      <p className="muted text-sm">
        An account lets the control centre reach you and lets you follow your
        report.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <ErrorBanner message={error} />

        <Field label="Full name" required error={fieldErrors.full_name}>
          <TextInput
            name="full_name"
            autoComplete="name"
            required
            value={form.full_name}
            onChange={(event) => update("full_name", event.target.value)}
          />
        </Field>

        <Field label="Email address" required error={fieldErrors.email}>
          <TextInput
            type="email"
            name="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={(event) => update("email", event.target.value)}
          />
        </Field>

        <Field
          label="Phone number"
          hint="Optional, but it lets an operator call you back."
          error={fieldErrors.phone}
        >
          <TextInput
            type="tel"
            name="phone"
            autoComplete="tel"
            value={form.phone}
            onChange={(event) => update("phone", event.target.value)}
          />
        </Field>

        <Field
          label="Password"
          required
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          error={fieldErrors.password}
        >
          <TextInput
            type="password"
            name="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={form.password}
            onChange={(event) => update("password", event.target.value)}
          />
        </Field>

        <Button type="submit" loading={submitting} className="w-full">
          Create account
        </Button>
      </form>

      <p className="muted text-sm">
        Already registered?{" "}
        <Link href="/login" className="text-brand-600 font-medium underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
