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
      <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="font-bold tracking-tight">
          RAKSHA<span className="text-brand-600"> RESPONDER</span>
        </Link>

        <nav className="flex items-center gap-2 text-sm">
          {loading ? null : user ? (
            <>
              <span className="muted hidden sm:inline">{user.full_name}</span>
              <NotificationBell
              api={getApiClient()}
              hrefFor={(n) => n.dispatch_id ? `/assignments/${n.dispatch_id}` : null}
              navigate={(href) => router.push(href)}
            />
              <Button variant="secondary" onClick={() => void signOut()}>
                Sign out
              </Button>
            </>
          ) : (
            <Link href="/login" className="font-semibold text-brand-600">
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
