"use client";

import { useState } from "react";

import {
  ApiError,
  USER_ROLES,
  roleLabel,
  type AdminUser,
  type UserRole,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import {
  EMPTY_USER_FORM,
  assignableRoles,
  generatePassword,
  validateUserForm,
  type UserFormErrors,
} from "@/lib/userAdmin";

/**
 * Create an account. The password is set here and cannot be recovered
 * afterwards, so after creation the screen shows it once for the administrator
 * to hand over securely. (There is no self-service password change yet — see
 * docs/FRONTEND.md.)
 */
export function UserCreateForm({
  actorRole,
  onCreated,
  onCancel,
}: {
  actorRole: UserRole;
  onCreated: (user: AdminUser) => void;
  onCancel: () => void;
}) {
  const api = getApiClient();
  const [values, setValues] = useState(EMPTY_USER_FORM);
  const [errors, setErrors] = useState<UserFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ user: AdminUser; password: string } | null>(null);

  const set = (key: keyof typeof values) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const result = validateUserForm(values);
    setErrors(result.errors);
    if (!result.input) return;
    setBusy(true);
    setServerError(null);
    try {
      const user = await api.createUser(result.input);
      setCreated({ user, password: result.input.password });
    } catch (caught) {
      setServerError(caught instanceof ApiError ? caught.message : "The account could not be created.");
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div role="status" className="space-y-3">
        <p className="font-semibold">
          Account created for {created.user.full_name} ({roleLabel(created.user.role)}).
        </p>
        <p className="text-sm">Initial password — shown once, not stored anywhere you can read it later:</p>
        <p className="surface rounded-lg px-3 py-2 font-mono text-sm select-all" aria-label="Initial password">
          {created.password}
        </p>
        <p className="muted text-xs">
          Hand it over through a secure channel. The user cannot change it themselves yet, so
          treat it as long-lived.
        </p>
        <Button onClick={() => onCreated(created.user)}>Done</Button>
      </div>
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="space-y-3">
      <ErrorBanner message={serverError} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Email" required error={errors.email}>
          <TextInput type="email" autoComplete="off" value={values.email} onChange={(e) => set("email")(e.target.value)} />
        </Field>
        <Field label="Full name" required error={errors.full_name}>
          <TextInput value={values.full_name} onChange={(e) => set("full_name")(e.target.value)} />
        </Field>
        <Field label="Phone" error={errors.phone}>
          <TextInput value={values.phone} onChange={(e) => set("phone")(e.target.value)} />
        </Field>
        <Field label="Role" required>
          <select
            aria-label="Role"
            className="surface w-full rounded-lg px-3 py-2.5 text-sm"
            value={values.role}
            onChange={(e) => set("role")(e.target.value)}
          >
            {assignableRoles(actorRole, USER_ROLES).map((role) => (
              <option key={role} value={role}>
                {roleLabel(role)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Initial password" required error={errors.password} hint="Generate one, or type your own; the server applies its password rules.">
        <div className="flex gap-2">
          <TextInput
            autoComplete="new-password"
            className="font-mono"
            value={values.password}
            onChange={(e) => set("password")(e.target.value)}
          />
          <Button type="button" variant="secondary" onClick={() => set("password")(generatePassword())}>
            Generate
          </Button>
        </div>
      </Field>
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          Create account
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
