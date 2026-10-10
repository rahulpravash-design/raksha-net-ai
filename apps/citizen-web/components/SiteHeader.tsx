"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { NotificationBell } from "@raksha/ui";

import { getApiClient } from "@/lib/api";

import { useAuth } from "./AuthProvider";
import { Button } from "./ui";

export function SiteHeader() {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();

  return (
    <header className="surface border-x-0 border-t-0">
      <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="font-bold tracking-tight">
          RAKSHA<span className="text-brand-600"> NET AI</span>
        </Link>

        <nav className="flex items-center gap-2 text-sm">
          {loading ? null : user ? (
            <>
              <Link href="/reports" className="px-2 py-1 hover:underline">
                My reports
              </Link>
              <Link
                href="/report"
                className="rounded-lg bg-red-600 px-3 py-1.5 font-semibold text-white hover:bg-red-700"
              >
                Report
              </Link>
              <NotificationBell
              api={getApiClient()}
              hrefFor={(n) => n.incident_id ? `/reports/${n.incident_id}` : null}
              navigate={(href) => router.push(href)}
            />
              <Button variant="secondary" onClick={() => void signOut()}>
                Sign out
              </Button>
            </>
          ) : (
            <>
              <Link href="/login" className="px-2 py-1 hover:underline">
                Sign in
              </Link>
              <Link
                href="/register"
                className="rounded-lg bg-brand-600 px-3 py-1.5 font-semibold text-white hover:bg-brand-700"
              >
                Create account
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
