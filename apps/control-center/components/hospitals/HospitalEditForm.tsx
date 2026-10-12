"use client";

import { useState } from "react";

import { ApiError, type Hospital } from "@raksha/api-client";

import { Button, ErrorBanner, Field, TextInput } from "@/components/ui";
import { getApiClient } from "@/lib/api";
import {
  buildDetailsUpdate,
  detailsFormFrom,
  type DetailsFormErrors,
} from "@/lib/hospital";

import { useHospitalOperators } from "./useHospitalOperators";

/**
 * Correct what a hospital *is* (administrators only): name, position, address,
 * phone and which operator maintains it, or retire it. Capacity is not here — it
 * is reported by the hospital's own operator on the capacity form, and the code is
 * the hospital's identity and cannot be changed.
 */
export function HospitalEditForm({
  hospital,
  onSaved,
  onCancel,
}: {
  hospital: Hospital;
  onSaved: (hospital: Hospital) => void;
  onCancel: () => void;
}) {
  const api = getApiClient();
  const operators = useHospitalOperators();
  const [values, setValues] = useState(() => detailsFormFrom(hospital));
  const [errors, setErrors] = useState<DetailsFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingRetire, setConfirmingRetire] = useState(false);

  const set = (key: keyof typeof values) => (value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  // The current operator may be missing from the active list (deactivated since):
  // keep them selectable so saving does not silently unlink them.
  const current = hospital.managed_by;
  const choices = operators.some((o) => o.id === current?.id) || !current
    ? operators
    : [...operators, { id: current.id, full_name: current.full_name, email: "no longer listed" }];

  async function run(action: () => Promise<Hospital>, fallback: string) {
    setBusy(true);
    setServerError(null);
    try {
      onSaved(await action());
    } catch (caught) {
      setServerError(caught instanceof ApiError ? caught.message : fallback);
      setConfirmingRetire(false);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const result = buildDetailsUpdate(hospital, values);
    setErrors(result.errors);
    if (!result.input) return;
    if (Object.keys(result.input).length === 0) {
      setServerError("Nothing has changed.");
      return;
    }
    const input = result.input;
    void run(() => api.updateHospital(hospital.id, input), "The hospital could not be updated.");
  }

  const text = (
    key: keyof typeof values,
    label: string,
    extra?: { required?: boolean; mode?: "decimal" },
  ) => (
    <Field label={label} required={extra?.required} error={errors[key]}>
      <TextInput
        inputMode={extra?.mode}
        value={values[key]}
        onChange={(e) => set(key)(e.target.value)}
      />
    </Field>
  );

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label="Edit hospital details"
      className="space-y-3"
    >
      <p className="muted text-xs">
        Code <strong>{hospital.code}</strong> identifies this hospital and cannot be changed.
        Beds and the accepting-emergencies flag are reported by the hospital&apos;s own operator.
      </p>
      <ErrorBanner message={serverError} />
      {text("name", "Name", { required: true })}
      <div className="grid gap-3 sm:grid-cols-2">
        {text("latitude", "Latitude", { required: true, mode: "decimal" })}
        {text("longitude", "Longitude", { required: true, mode: "decimal" })}
      </div>
      {text("address", "Address")}
      {text("contact_phone", "Contact phone")}
      <Field
        label="Hospital operator"
        hint="Who maintains this hospital's capacity and sees its inbound patients. Changing it takes effect at once: the previous operator loses access to this hospital."
      >
        <select
          aria-label="Hospital operator"
          className="surface w-full rounded-lg px-3 py-2.5 text-sm"
          value={values.managed_by_id}
          onChange={(e) => set("managed_by_id")(e.target.value)}
        >
          <option value="">Not linked</option>
          {choices.map((operator) => (
            <option key={operator.id} value={operator.id}>
              {operator.full_name} ({operator.email})
            </option>
          ))}
        </select>
      </Field>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy && !confirmingRetire}>
          Save changes
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>

      <div className="space-y-2 border-t border-[var(--border)] pt-3">
        {hospital.is_active ? (
          confirmingRetire ? (
            <div role="group" aria-label="Retire this hospital" className="space-y-2">
              <p className="text-sm">
                Retiring removes {hospital.name} from the hospital list and from nearby searches.
                It is refused while the hospital has open inbound-patient notices. You can restore
                it later.
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="danger"
                  loading={busy}
                  onClick={() =>
                    void run(
                      () => api.updateHospital(hospital.id, { is_active: false }),
                      "The hospital could not be retired.",
                    )
                  }
                >
                  Confirm retire
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={busy}
                  onClick={() => setConfirmingRetire(false)}
                >
                  Keep it
                </Button>
              </div>
            </div>
          ) : (
            <Button type="button" variant="danger" onClick={() => setConfirmingRetire(true)}>
              Retire this hospital…
            </Button>
          )
        ) : (
          <Button
            type="button"
            variant="secondary"
            loading={busy}
            onClick={() =>
              void run(
                () => api.updateHospital(hospital.id, { is_active: true }),
                "The hospital could not be restored.",
              )
            }
          >
            Restore this hospital
          </Button>
        )}
      </div>
    </form>
  );
}
