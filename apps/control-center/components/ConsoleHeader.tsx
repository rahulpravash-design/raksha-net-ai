"use client";

import Link from "next/link";

import { useAuth } from "./AuthProvider";
import { Button } from "./ui";

export function ConsoleHeader() {
  const { user, loading, signOut } = useAuth();

  return (
    <header className="surface border-x-0 border-t-0">
      <div className="mx-auto flex w-full max-w-[110rem] items-center justify-between gap-4 px-4 py-3">
        <Link href="/dashboard" className="font-bold tracking-tight">
          RAKSHA<span className="text-brand-600"> CONTROL CENTRE</span>
        </Link>

        {loading ? null : user ? (
          <div className="flex items-center gap-4 text-sm">
            <span className="muted hidden sm:inline">
              {user.full_name} · {user.role.replace(/_/g, " ").toLowerCase()}
            </span>
            <Button variant="secondary" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
