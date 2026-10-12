"use client";

import { useState } from "react";

import { ApiError, type Hospital } from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import {
  buildCapacityUpdate,
  capacityFormFrom,
  isEmptyUpdate,
  type CapacityFormErrors,
} from "@/lib/hospital";

/** Report current capacity. Only changed fields are sent; the audit log records who. */
export function CapacityForm({
  hospital,
  onSaved,
  onCancel,
}: {
  hospital: Hospital;
  onSaved: (hospital: Hospital) => void;
  onCancel: () => void;
}) {
  const api = getApiClient();
  const [values, setValues] = useState(() => capacityFormFrom(hospital));
  const [errors, setErrors] = useState<CapacityFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof values) => (value: string | boolean) =>
    setValues((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const { errors: found, input } = buildCapacityUpdate(hospital, values);
    setErrors(found);
    if (!input) return;
    if (isEmptyUpdate(input)) {
      setServerError("Nothing has changed.");
      return;
    }
    setBusy(true);
    setServerError(null);
    try {
      onSaved(await api.updateHospitalCapacity(hospital.id, input));
    } catch (caught) {
      setServerError(caught instanceof ApiError ? caught.message : "The report could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className="space-y-3">
      <ErrorBanner message={serverError} />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Free beds" error={errors.available_beds}>
          <TextInput inputMode="numeric" value={values.available_beds} onChange={(e) => set("available_beds")(e.target.value)} />
        </Field>
        <Field label="Total beds" error={errors.total_beds}>
          <TextInput inputMode="numeric" value={values.total_beds} onChange={(e) => set("total_beds")(e.target.value)} />
        </Field>
        <Field label="Free ICU beds" error={errors.icu_available}>
          <TextInput inputMode="numeric" value={values.icu_available} onChange={(e) => set("icu_available")(e.target.value)} />
        </Field>
        <Field label="Total ICU beds" error={errors.icu_total}>
          <TextInput inputMode="numeric" value={values.icu_total} onChange={(e) => set("icu_total")(e.target.value)} />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={values.accepting_emergencies}
          onChange={(e) => set("accepting_emergencies")(e.target.checked)}
        />
        Accepting emergency patients
      </label>
      <Field label="Specialties" hint="Comma separated, e.g. trauma, burns, cardiac.">
        <TextInput value={values.specialties} onChange={(e) => set("specialties")(e.target.value)} />
      </Field>
      <Field label="Note" hint="Optional. Recorded in the audit log." error={errors.note}>
        <TextInput value={values.note} onChange={(e) => set("note")(e.target.value)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          Report capacity
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
