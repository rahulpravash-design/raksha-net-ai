"use client";

import { MfaPanel, groupSecret } from "@raksha/ui";

import { useAuth } from "@/components/AuthProvider";
import { getApiClient } from "@/lib/api";

export { groupSecret };

/** Two-factor authentication for the signed-in user (the panel is shared with the other apps). */
export function MfaSettings() {
  const { user, refreshUser } = useAuth();
  if (!user) return null;
  return (
    <MfaPanel
      api={getApiClient()}
      user={user}
      onChanged={refreshUser}
      className="panel-3d space-y-4 rounded-xl p-4"
    />
  );
}
