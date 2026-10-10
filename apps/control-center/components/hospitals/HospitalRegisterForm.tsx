"use client";

import { useEffect, useState } from "react";

import { ApiError, type AdminUser, type Hospital } from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import {
  EMPTY_HOSPITAL_FORM,
  validateHospitalForm,
  type HospitalFormErrors,
} from "@/lib/hospital";

/** Register a hospital (administrators only) and link the operator who maintains it. */
export function HospitalRegisterForm({
  onCreated,
  onCancel,
}: {
  onCreated: (hospital: Hospital) => void;
  onCancel: () => void;
}) {
  const api = getApiClient();
  const [values, setValues] = useState(EMPTY_HOSPITAL_FORM);
  const [errors, setErrors] = useState<HospitalFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [operators, setOperators] = useState<AdminUser[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .adminUsers({ role: "HOSPITAL_OPERATOR", is_active: true, page_size: 100 })
      .then((page) => {
        if (!cancelled) setOperators(page.items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [api]);

  const set = (key: keyof typeof values) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const result = validateHospitalForm(values);
    setErrors(result.errors);
    if (!result.input) return;
    setBusy(true);
    setServerError(null);
    try {
      onCreated(await api.createHospital(result.input));
    } catch (caught) {
      setServerError(caught instanceof ApiError ? caught.message : "The hospital could not be registered.");
    } finally {
      setBusy(false);
    }
  }

  const text = (key: keyof typeof values, label: string, extra?: { required?: boolean; hint?: string; mode?: "numeric" | "decimal" }) => (
    <Field label={label} required={extra?.required} hint={extra?.hint} error={errors[key]}>
      <TextInput inputMode={extra?.mode} value={values[key]} onChange={(e) => set(key)(e.target.value)} />
    </Field>
  );

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="space-y-3">
      <ErrorBanner message={serverError} />
      <div className="grid gap-3 sm:grid-cols-2">
        {text("code", "Code", { required: true })}
        {text("name", "Name", { required: true })}
        {text("latitude", "Latitude", { required: true, mode: "decimal" })}
        {text("longitude", "Longitude", { required: true, mode: "decimal" })}
        {text("total_beds", "Total beds", { mode: "numeric" })}
        {text("available_beds", "Free beds", { mode: "numeric" })}
        {text("icu_total", "Total ICU beds", { mode: "numeric" })}
        {text("icu_available", "Free ICU beds", { mode: "numeric" })}
      </div>
      {text("address", "Address")}
      {text("contact_phone", "Contact phone")}
      {text("specialties", "Specialties", { hint: "Comma separated, e.g. trauma, burns." })}
      <Field
        label="Hospital operator"
        hint="Who maintains this hospital's capacity and sees its inbound patients. Only active hospital-operator accounts are listed."
      >
        <select
          aria-label="Hospital operator"
          className="surface w-full rounded-lg px-3 py-2.5 text-sm"
          value={values.managed_by_id}
          onChange={(e) => set("managed_by_id")(e.target.value)}
        >
          <option value="">Not linked yet</option>
          {operators.map((operator) => (
            <option key={operator.id} value={operator.id}>
              {operator.full_name} ({operator.email})
            </option>
          ))}
        </select>
      </Field>
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          Register hospital
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
