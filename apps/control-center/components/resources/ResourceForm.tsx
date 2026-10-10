"use client";

import { useEffect, useState } from "react";

import {
  RESOURCE_TYPES,
  resourceTypeLabel,
  type CreateResourceInput,
  type UserSummary,
} from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import {
  validateResourceForm,
  type ResourceFormErrors,
  type ResourceFormValues,
} from "@/lib/resourceForm";

/**
 * Create / edit form. Validation catches typing mistakes; the server decides
 * everything else (call-sign uniqueness, coordinates inside the deployment
 * area) and its message is shown verbatim.
 */
export function ResourceForm({
  mode,
  initial,
  onSubmit,
  onCancel,
}: {
  mode: "create" | "edit";
  initial: ResourceFormValues;
  /** Resolve to an error message to show, or null on success. */
  onSubmit: (input: CreateResourceInput) => Promise<string | null>;
  onCancel: () => void;
}) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<ResourceFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [crew, setCrew] = useState<UserSummary[]>([]);

  useEffect(() => {
    // Best effort: without the directory the unit is simply created unlinked.
    let cancelled = false;
    getApiClient()
      .responderDirectory()
      .then((rows) => {
        if (!cancelled) setCrew(rows);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const set = (key: keyof ResourceFormValues) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const result = validateResourceForm(values, mode);
    setErrors(result.errors);
    if (!result.input) return;
    setBusy(true);
    setServerError(null);
    const message = await onSubmit(result.input);
    setBusy(false);
    if (message) setServerError(message);
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="space-y-3">
      <ErrorBanner message={serverError} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Call sign" required error={errors.call_sign} hint={mode === "edit" ? "Fixed once registered." : undefined}>
          <TextInput
            value={values.call_sign}
            disabled={mode === "edit"}
            onChange={(e) => set("call_sign")(e.target.value)}
          />
        </Field>
        <Field label="Name" required error={errors.name}>
          <TextInput value={values.name} onChange={(e) => set("name")(e.target.value)} />
        </Field>
        <Field label="Type" required>
          <select
            aria-label="Type"
            className="surface w-full rounded-lg px-3 py-2.5 text-sm"
            value={values.resource_type}
            onChange={(e) => set("resource_type")(e.target.value)}
          >
            {RESOURCE_TYPES.map((type) => (
              <option key={type} value={type}>
                {resourceTypeLabel(type)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Crew size" error={errors.crew_size}>
          <TextInput
            inputMode="numeric"
            value={values.crew_size}
            onChange={(e) => set("crew_size")(e.target.value)}
          />
        </Field>
        <Field label="Latitude" required error={errors.latitude}>
          <TextInput
            inputMode="decimal"
            value={values.latitude}
            onChange={(e) => set("latitude")(e.target.value)}
          />
        </Field>
        <Field label="Longitude" required error={errors.longitude}>
          <TextInput
            inputMode="decimal"
            value={values.longitude}
            onChange={(e) => set("longitude")(e.target.value)}
          />
        </Field>
      </div>
      <Field label="Base address">
        <TextInput value={values.base_address} onChange={(e) => set("base_address")(e.target.value)} />
      </Field>
      <Field label="Capabilities" hint="Comma separated, e.g. als, oxygen, heavy_rescue." error={errors.capabilities}>
        <TextInput value={values.capabilities} onChange={(e) => set("capabilities")(e.target.value)} />
      </Field>
      <Field label="Crew member" hint="The responder who operates this unit and sees its assignments.">
        <select
          aria-label="Crew member"
          className="surface w-full rounded-lg px-3 py-2.5 text-sm"
          value={values.operator_id}
          onChange={(e) => set("operator_id")(e.target.value)}
        >
          <option value="">Not linked</option>
          {crew.map((member) => (
            <option key={member.id} value={member.id}>
              {member.full_name}
            </option>
          ))}
          {values.operator_id && !crew.some((m) => m.id === values.operator_id) && (
            <option value={values.operator_id}>Currently linked crew member</option>
          )}
        </select>
      </Field>
      <Field label="Contact phone">
        <TextInput value={values.contact_phone} onChange={(e) => set("contact_phone")(e.target.value)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          {mode === "create" ? "Register resource" : "Save changes"}
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
