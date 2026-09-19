"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, type ResponderAssignment } from "@raksha/api-client";

import { AssignmentCard } from "@/components/AssignmentCard";
import { useAuth } from "@/components/AuthProvider";
import { EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { getApiClient } from "@/lib/api";

/** Crews leave this open on a mount; a stale list is worse than a cheap poll. */
const REFRESH_MS = 20_000;

export default function AssignmentsPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [assignments, setAssignments] = useState<ResponderAssignment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAssignments(await api.myAssignments(true));
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) return;
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Your assignments could not be loaded.",
      );
      setAssignments([]);
    }
  }, [api]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // The session token lives in browser storage, so this cannot be fetched in
    // a server component; every setState here follows an awaited response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [authLoading, user, router, load]);

  if (authLoading || assignments === null) {
    return <Spinner label="Loading your assignments" />;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Your assignments</h1>
      <ErrorBanner message={error} />

      {assignments.length === 0 ? (
        <EmptyState
          title="Nothing assigned right now"
          body="When the control centre sends your unit to an incident, it will appear here."
        />
      ) : (
        <ul className="space-y-3">
          {assignments.map((assignment) => (
            <AssignmentCard key={assignment.id} assignment={assignment} />
          ))}
        </ul>
      )}
    </div>
  );
}
