"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { NotificationBell } from "@raksha/ui";

import { getApiClient } from "@/lib/api";

import { useAuth } from "./AuthProvider";
import { homeFor } from "@/lib/routes";

import { Button } from "./ui";

export function ConsoleHeader() {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();

  return (
    <header className="surface border-x-0 border-t-0">
      <div className="mx-auto flex w-full max-w-[110rem] items-center justify-between gap-4 px-4 py-3">
        <Link href={user ? homeFor(user.role) : "/dashboard"} className="font-bold tracking-tight">
          RAKSHA<span className="text-brand-600"> CONTROL CENTRE</span>
        </Link>

        {loading ? null : user ? (
          <div className="flex items-center gap-4 text-sm">
            <span className="muted hidden sm:inline">
              {user.full_name} · {user.role.replace(/_/g, " ").toLowerCase()}
            </span>
            <NotificationBell
              api={getApiClient()}
              hrefFor={(n) => n.incident_id ? `/incidents/${n.incident_id}` : null}
              navigate={(href) => router.push(href)}
            />
            <Link href="/account/security" className="text-sm font-semibold underline-offset-4 hover:underline">
              Security
            </Link>
            <Button variant="secondary" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
