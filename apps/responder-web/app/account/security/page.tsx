"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { MfaPanel, PasswordPanel } from "@raksha/ui";

import { useAuth } from "@/components/AuthProvider";
import { Spinner } from "@/components/ui";
import { getApiClient } from "@/lib/api";

/**
 * Account security. Deliberately loads nothing but the signed-in user: when
 * two-factor is required by policy, or an administrator-set password is still in
 * force, the API refuses every other endpoint until that is dealt with, and this
 * is where those users are sent.
 */
export default function SecurityPage() {
  const router = useRouter();
  const { user, loading, refreshUser } = useAuth();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) return <Spinner label="Loading your account" />;
  const api = getApiClient();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Account security</h1>
        <p className="muted text-sm">
          {user.full_name} · {user.email}
        </p>
      </div>
      <PasswordPanel
        api={api}
        user={user}
        onChanged={refreshUser}
        onForcedChangeDone={() => router.replace("/assignments")}
      />
      <MfaPanel api={api} user={user} onChanged={refreshUser} />
    </div>
  );
}
