"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { ApiError } from "@raksha/api-client";
import { SecondFactorField } from "@raksha/ui";

import { useAuth } from "@/components/AuthProvider";
import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const { signIn, user, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/assignments");
  }, [loading, user, router]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email, password, needsCode ? code : undefined);
      router.push("/assignments");
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "MFA_REQUIRED") {
        setNeedsCode(true);
        setError(
          "Enter the 6-digit code from your authenticator app, or one of your recovery codes.",
        );
      } else {
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Could not reach the server. Check your connection.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-bold">Responder sign in</h1>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <ErrorBanner message={error} />

        <Field label="Email address" required>
          <TextInput
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>

        <Field label="Password" required>
          <TextInput
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        {needsCode && <SecondFactorField value={code} onChange={setCode} />}
        <p className="text-sm">
          <Link href="/forgot-password" className="font-medium underline">
            Forgot your password?
          </Link>
        </p>

        <Button type="submit" loading={submitting} className="w-full">
          Sign in
        </Button>
      </form>
    </div>
  );
}
