"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  categoryLabel,
  formatRelative,
  type IncidentSummary,
} from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import {
  EmptyState,
  ErrorBanner,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { getApiClient } from "@/lib/api";

export default function MyReportsPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [reports, setReports] = useState<IncidentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const page = await api.myIncidents({ sort: "-created_at", page_size: 50 });
      setReports(page.items);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Your reports could not be loaded.",
      );
      setReports([]);
    }
  }, [api]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // The session token lives in browser storage, so this data cannot be
    // fetched in a server component — it has to be loaded on mount. The rule
    // guards against cascading synchronous renders; every setState here
    // happens after an awaited response, which is not that case.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [authLoading, user, router, load]);

  if (authLoading || reports === null) return <Spinner label="Loading your reports" />;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">My reports</h1>
        <Link
          href="/report"
          className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
        >
          New report
        </Link>
      </div>

      <ErrorBanner message={error} />

      {reports.length === 0 ? (
        <EmptyState
          title="You have not filed any reports"
          body="When you report an emergency it will appear here, with its reference code and current status."
        />
      ) : (
        <ul className="space-y-3">
          {reports.map((report) => (
            <li key={report.id}>
              <Link
                href={`/reports/${report.id}`}
                className="surface block rounded-xl p-4 transition hover:border-brand-500"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">
                    {categoryLabel(report.category)}
                  </span>
                  <StatusBadge status={report.status} />
                </div>
                <p className="muted mt-1 text-sm">
                  {report.reference_code} · {formatRelative(report.created_at)}
                </p>
                {report.address_text && (
                  <p className="muted mt-1 truncate text-sm">
                    {report.address_text}
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
