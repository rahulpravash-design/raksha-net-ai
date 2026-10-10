"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/AuthProvider";
import { MfaSettings } from "@/components/MfaSettings";
import { Spinner } from "@/components/ui";

/**
 * Account security. Deliberately loads nothing but the signed-in user: when
 * two-factor is required by policy the API refuses every other endpoint until it
 * is set up, and this is where those users are sent.
 */
export default function SecurityPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) return <Spinner label="Loading your account" />;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-lg font-bold tracking-wide">ACCOUNT SECURITY</h1>
        <p className="muted text-xs">
          {user.full_name} · {user.email}
        </p>
      </div>
      <MfaSettings />
    </div>
  );
}
