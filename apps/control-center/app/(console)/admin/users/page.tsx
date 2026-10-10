"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  USER_ROLES,
  formatRelative,
  isAdminRole,
  isLockedNow,
  roleLabel,
  type AdminUser,
  type Page,
  type UserRole,
} from "@raksha/api-client";

import { useAuth } from "@/components/AuthProvider";
import { UserCreateForm } from "@/components/admin/UserCreateForm";
import { UserDetail } from "@/components/admin/UserDetail";
import { Button, EmptyState, ErrorBanner, Spinner, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import { homeFor } from "@/lib/routes";

const PAGE_SIZE = 20;

export default function AdminUsersPage() {
  const router = useRouter();
  const api = getApiClient();
  const { user, loading: authLoading } = useAuth();

  const [result, setResult] = useState<Page<AdminUser> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<UserRole | "">("");
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    try {
      setResult(
        await api.adminUsers({
          page,
          page_size: PAGE_SIZE,
          ...(search.trim() ? { q: search.trim() } : {}),
          ...(role ? { role } : {}),
          ...(activeFilter ? { is_active: activeFilter === "true" } : {}),
        }),
      );
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) return;
      setError(caught instanceof ApiError ? caught.message : "Accounts could not be loaded.");
    }
  }, [api, page, search, role, activeFilter]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (!isAdminRole(user.role)) {
      // The API refuses this screen's data to everyone else.
      router.replace(homeFor(user.role));
      return;
    }
    // Session token is in browser storage; every setState follows an await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [authLoading, user, router, load]);

  const selected = result?.items.find((item) => item.id === selectedId) ?? null;
  const filter = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setPage(1);
  };

  if (authLoading || !user || !isAdminRole(user.role)) return <Spinner label="Loading accounts" />;
  if (!result && !error) return <Spinner label="Loading accounts" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-wide">ACCOUNTS</h1>
          <p className="muted text-xs">
            Create operators, change roles, unlock accounts and reset a lost second factor. Every
            action here is recorded in the audit log.
          </p>
        </div>
        {!creating && <Button onClick={() => setCreating(true)}>Create an account</Button>}
      </div>

      <ErrorBanner message={error} />

      {creating && (
        <section className="panel-3d rounded-xl p-4">
          <h2 className="mb-3 font-semibold">Create an account</h2>
          <UserCreateForm
            actorRole={user.role}
            onCancel={() => setCreating(false)}
            onCreated={(created) => {
              setCreating(false);
              setSelectedId(created.id);
              void load();
            }}
          />
        </section>
      )}

      <div className="panel-3d grid gap-2 rounded-xl p-3 sm:grid-cols-3">
        <TextInput
          type="search"
          aria-label="Search accounts"
          placeholder="Search name or email"
          value={search}
          onChange={(e) => filter(setSearch)(e.target.value)}
        />
        <select
          aria-label="Filter by role"
          className="surface rounded-lg px-2 py-2 text-sm"
          value={role}
          onChange={(e) => filter(setRole)(e.target.value as UserRole | "")}
        >
          <option value="">All roles</option>
          {USER_ROLES.map((value) => (
            <option key={value} value={value}>
              {roleLabel(value)}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by status"
          className="surface rounded-lg px-2 py-2 text-sm"
          value={activeFilter}
          onChange={(e) => filter(setActiveFilter)(e.target.value as "" | "true" | "false")}
        >
          <option value="">Active and deactivated</option>
          <option value="true">Active only</option>
          <option value="false">Deactivated only</option>
        </select>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="space-y-3">
          {result && result.items.length === 0 ? (
            <EmptyState title="No accounts match" body="Try clearing a filter." />
          ) : (
            <ul className="space-y-2" aria-label="Accounts">
              {result?.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    aria-current={item.id === selectedId ? "true" : undefined}
                    className={`panel-3d flex w-full flex-wrap items-center justify-between gap-2 rounded-xl p-3 text-left ${
                      item.id === selectedId ? "border-[var(--accent)]!" : ""
                    } ${item.is_active ? "" : "opacity-60"}`}
                  >
                    <span>
                      <span className="block font-semibold">{item.full_name}</span>
                      <span className="muted block text-xs">{item.email}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="rounded-full border border-[var(--border)] px-2 py-0.5">
                        {roleLabel(item.role)}
                      </span>
                      {!item.is_active && <span className="rounded-full border border-amber-300/60 px-2 py-0.5 text-amber-200">Deactivated</span>}
                      {isLockedNow(item) && <span className="rounded-full border border-red-400/60 px-2 py-0.5 text-red-300">Locked</span>}
                      <span className="rounded-full border border-[var(--border)] px-2 py-0.5">
                        {item.mfa_enabled ? "2FA on" : "2FA off"}
                      </span>
                      <span className="muted">
                        {item.last_login_at ? `Signed in ${formatRelative(item.last_login_at)}` : "Never signed in"}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {result && result.pages > 1 && (
            <nav aria-label="Pagination" className="flex items-center justify-between text-sm">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <span className="muted">
                Page {result.page} of {result.pages} · {result.total} accounts
              </span>
              <Button variant="secondary" disabled={page >= result.pages} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </nav>
          )}
        </div>

        <div>
          {selected ? (
            <UserDetail
              key={selected.id}
              user={selected}
              actor={{ id: user.id, role: user.role }}
              onChanged={() => void load()}
            />
          ) : (
            <p className="panel-3d muted rounded-xl p-4 text-sm">Select an account to manage it.</p>
          )}
        </div>
      </div>
    </div>
  );
}
