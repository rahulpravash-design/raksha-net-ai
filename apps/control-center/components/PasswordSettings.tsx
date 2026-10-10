"use client";

import { useRouter } from "next/navigation";

import { PasswordPanel } from "@raksha/ui";

import { useAuth } from "@/components/AuthProvider";
import { getApiClient } from "@/lib/api";
import { homeFor } from "@/lib/routes";

/** Change your own password (the panel is shared with the other apps). */
export function PasswordSettings() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  if (!user) return null;
  return (
    <PasswordPanel
      api={getApiClient()}
      user={user}
      onChanged={refreshUser}
      onForcedChangeDone={() => router.replace(homeFor(user.role))}
      className="panel-3d space-y-4 rounded-xl p-4"
    />
  );
}
