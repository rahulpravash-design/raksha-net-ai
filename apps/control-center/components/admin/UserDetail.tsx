"use client";

import { useState } from "react";

import {
  ApiError,
  USER_ROLES,
  formatDateTime,
  isLockedNow,
  roleLabel,
  type AdminUser,
  type UserRole,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import {
  assignableRoles,
  generatePassword,
  permissionsFor,
} from "@/lib/userAdmin";

type Confirming = "deactivate" | "reset-mfa" | "reset-password" | "role" | null;

/** One account: profile edit, role/active, unlock, and MFA reset — each audited server-side. */
export function UserDetail({
  user,
  actor,
  onChanged,
}: {
  user: AdminUser;
  actor: { id: string; role: UserRole };
  onChanged: (user: AdminUser) => void;
}) {
  const api = getApiClient();
  const perms = permissionsFor(actor, user);
  const locked = isLockedNow(user);
  const [name, setName] = useState(user.full_name);
  const [phone, setPhone] = useState(user.phone ?? "");
  const [role, setRole] = useState<UserRole>(user.role);
  const [confirming, setConfirming] = useState<Confirming>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState("");
  const [shownPassword, setShownPassword] = useState<string | null>(null);

  async function run(
    action: () => Promise<AdminUser>,
    done: string,
  ): Promise<boolean> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      onChanged(await action());
      setNotice(done);
      setConfirming(null);
      return true;
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "That action could not be completed.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  }

  const profileChanged =
    name.trim() !== user.full_name || phone.trim() !== (user.phone ?? "");

  return (
    <section
      aria-label="User detail"
      className="panel-3d space-y-4 rounded-xl p-4"
    >
      <div>
        <h2 className="text-lg font-bold">{user.full_name}</h2>
        <p className="muted text-sm">{user.email}</p>
      </div>

      <ErrorBanner message={error} />
      {notice && (
        <p role="status" className="text-sm text-[var(--accent)]">
          {notice}
        </p>
      )}
      {perms.reason && <p className="muted text-xs">{perms.reason}</p>}

      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="muted">Role</dt>
          <dd className="font-medium">{roleLabel(user.role)}</dd>
        </div>
        <div>
          <dt className="muted">Account</dt>
          <dd className="font-medium">
            {user.is_active ? "Active" : "Deactivated"}
          </dd>
        </div>
        <div>
          <dt className="muted">Two-factor</dt>
          <dd className="font-medium">{user.mfa_enabled ? "On" : "Off"}</dd>
        </div>
        <div>
          <dt className="muted">Password</dt>
          <dd className="font-medium">
            {user.must_change_password
              ? "Set by an administrator — must be changed at next sign-in"
              : "Chosen by the user"}
          </dd>
        </div>
        <div>
          <dt className="muted">Sign-in</dt>
          <dd className="font-medium">
            {locked
              ? `Locked until ${formatDateTime(user.locked_until as string)}`
              : "Not locked"}
            {user.failed_login_attempts > 0
              ? ` · ${user.failed_login_attempts} failed attempts`
              : ""}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="muted">Last signed in</dt>
          <dd>
            {user.last_login_at ? formatDateTime(user.last_login_at) : "Never"}
          </dd>
        </div>
      </dl>

      {perms.canEditProfile && (
        <div className="space-y-3 border-t border-[var(--border)] pt-3">
          <h3 className="text-sm font-semibold">Profile</h3>
          <Field label="Full name">
            <TextInput value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Phone">
            <TextInput
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </Field>
          <Button
            variant="secondary"
            disabled={busy || !profileChanged || name.trim().length < 2}
            onClick={() =>
              void run(
                () =>
                  api.updateUser(user.id, {
                    ...(name.trim() !== user.full_name
                      ? { full_name: name.trim() }
                      : {}),
                    ...(phone.trim() !== (user.phone ?? "")
                      ? { phone: phone.trim() || null }
                      : {}),
                  }),
                "Profile saved.",
              )
            }
          >
            Save profile
          </Button>
        </div>
      )}

      {perms.canChangeRoleOrActive && (
        <div className="space-y-3 border-t border-[var(--border)] pt-3">
          <h3 className="text-sm font-semibold">Role and access</h3>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Role">
              <select
                aria-label="Change role"
                className="surface rounded-lg px-3 py-2.5 text-sm"
                value={role}
                onChange={(e) => {
                  setRole(e.target.value as UserRole);
                  setConfirming(null);
                }}
              >
                {assignableRoles(actor.role, USER_ROLES).map((value) => (
                  <option key={value} value={value}>
                    {roleLabel(value)}
                  </option>
                ))}
              </select>
            </Field>
            {role !== user.role && confirming !== "role" && (
              <Button variant="secondary" onClick={() => setConfirming("role")}>
                Change role…
              </Button>
            )}
          </div>
          {confirming === "role" && (
            <div
              role="group"
              aria-label="Confirm role change"
              className="space-y-2"
            >
              <p className="text-sm">
                Change {user.full_name} from {roleLabel(user.role)} to{" "}
                {roleLabel(role)}? This is recorded in the audit log.
              </p>
              <div className="flex gap-2">
                <Button
                  loading={busy}
                  onClick={() =>
                    void run(
                      () => api.updateUser(user.id, { role }),
                      "Role changed.",
                    )
                  }
                >
                  Confirm role change
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => {
                    setConfirming(null);
                    setRole(user.role);
                  }}
                >
                  Keep {roleLabel(user.role)}
                </Button>
              </div>
            </div>
          )}

          {user.is_active ? (
            confirming === "deactivate" ? (
              <div
                role="group"
                aria-label="Confirm deactivation"
                className="space-y-2"
              >
                <p className="text-sm">
                  Deactivate {user.full_name}? They will no longer be able to
                  sign in.
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    loading={busy}
                    onClick={() =>
                      void run(
                        () => api.updateUser(user.id, { is_active: false }),
                        "Account deactivated.",
                      )
                    }
                  >
                    Confirm deactivate
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setConfirming(null)}
                  >
                    Keep active
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="danger"
                onClick={() => setConfirming("deactivate")}
              >
                Deactivate…
              </Button>
            )
          ) : (
            <Button
              disabled={busy}
              onClick={() =>
                void run(
                  () => api.updateUser(user.id, { is_active: true }),
                  "Account reactivated.",
                )
              }
            >
              Reactivate
            </Button>
          )}
        </div>
      )}

      {(locked || perms.canResetMfa || perms.canResetPassword) && (
        <div className="space-y-3 border-t border-[var(--border)] pt-3">
          <h3 className="text-sm font-semibold">Recovery</h3>
          {locked && (
            <Button
              disabled={busy}
              onClick={() =>
                void run(() => api.unlockUser(user.id), "Account unlocked.")
              }
            >
              Unlock account
            </Button>
          )}
          {perms.canResetPassword &&
            (confirming === "reset-password" ? (
              <div
                role="group"
                aria-label="Set a temporary password"
                className="space-y-2"
              >
                <p className="text-sm">
                  Set a temporary password for {user.full_name}? Their other
                  sessions end, any lockout is cleared, and they must replace it
                  the first time they sign in.
                </p>
                <Field label="Temporary password">
                  <div className="flex gap-2">
                    <TextInput
                      autoComplete="new-password"
                      className="font-mono"
                      value={tempPassword}
                      onChange={(e) => setTempPassword(e.target.value)}
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setTempPassword(generatePassword())}
                    >
                      Generate
                    </Button>
                  </div>
                </Field>
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    loading={busy}
                    disabled={tempPassword === ""}
                    onClick={() => {
                      const chosen = tempPassword;
                      void run(
                        () => api.adminResetPassword(user.id, chosen),
                        "Temporary password set.",
                      ).then((ok) => {
                        if (!ok) return;
                        setShownPassword(chosen);
                        setTempPassword("");
                      });
                    }}
                  >
                    Confirm temporary password
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => {
                      setConfirming(null);
                      setTempPassword("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="danger"
                onClick={() => {
                  setConfirming("reset-password");
                  setShownPassword(null);
                }}
              >
                Set temporary password…
              </Button>
            ))}
          {shownPassword && (
            <div role="status" className="space-y-1">
              <p className="text-sm">Temporary password — shown once:</p>
              <p
                className="surface select-all rounded-lg px-3 py-2 font-mono text-sm"
                aria-label="Temporary password"
              >
                {shownPassword}
              </p>
              <p className="muted text-xs">
                Hand it over through a secure channel.
              </p>
            </div>
          )}
          {perms.canResetMfa &&
            (confirming === "reset-mfa" ? (
              <div
                role="group"
                aria-label="Confirm MFA reset"
                className="space-y-2"
              >
                <p className="text-sm">
                  Remove {user.full_name}&apos;s second factor and end all their
                  sessions? Use this for a lost or stolen phone, after
                  confirming who is asking.
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    loading={busy}
                    onClick={() =>
                      void run(
                        () => api.resetUserMfa(user.id),
                        "Two-factor removed and sessions ended.",
                      )
                    }
                  >
                    Confirm MFA reset
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setConfirming(null)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="danger"
                onClick={() => setConfirming("reset-mfa")}
              >
                Reset two-factor…
              </Button>
            ))}
        </div>
      )}
    </section>
  );
}
