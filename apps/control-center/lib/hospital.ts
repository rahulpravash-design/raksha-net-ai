import type { CreateHospitalInput, Hospital, HospitalCapacityInput } from "@raksha/api-client";

import { parseCapabilities } from "./resourceForm";

/**
 * Capacity is reported by hand, several times a shift. After this long without a
 * report the figures may no longer be true, and the screen says so rather than
 * presenting stale beds as fact. (A display convention, not a backend rule.)
 */
export const CAPACITY_STALE_HOURS = 6;

export function capacityAgeHours(updatedAt: string | null, now = Date.now()): number | null {
  if (!updatedAt) return null;
  const then = new Date(updatedAt).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, (now - then) / 3_600_000);
}

export function isCapacityStale(updatedAt: string | null, now = Date.now()): boolean {
  const age = capacityAgeHours(updatedAt, now);
  return age === null || age > CAPACITY_STALE_HOURS;
}

/** Share of beds free, 0–1; 0 when the hospital reports no beds. */
export function freeShare(available: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(1, Math.max(0, available / total));
}

export interface CapacityFormValues {
  available_beds: string;
  total_beds: string;
  icu_available: string;
  icu_total: string;
  accepting_emergencies: boolean;
  specialties: string;
  note: string;
}

export type CapacityFormErrors = Partial<Record<keyof CapacityFormValues, string>>;

export function capacityFormFrom(hospital: Hospital): CapacityFormValues {
  return {
    available_beds: String(hospital.available_beds),
    total_beds: String(hospital.total_beds),
    icu_available: String(hospital.icu_available),
    icu_total: String(hospital.icu_total),
    accepting_emergencies: hospital.accepting_emergencies,
    specialties: hospital.specialties.join(", "),
    note: "",
  };
}

function count(text: string): number {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return Number.NaN;
  return Number(trimmed);
}

/**
 * Validate a capacity report and return only what changed. The cross-field rule
 * (free cannot exceed total) is checked on the resulting values, as the server
 * does, so lowering the total below the free count is caught here.
 */
export function buildCapacityUpdate(
  hospital: Hospital,
  values: CapacityFormValues,
): { errors: CapacityFormErrors; input: HospitalCapacityInput | null } {
  const errors: CapacityFormErrors = {};
  const fields = ["available_beds", "total_beds", "icu_available", "icu_total"] as const;
  const parsed = {} as Record<(typeof fields)[number], number>;
  for (const field of fields) {
    const value = count(values[field]);
    if (Number.isNaN(value) || value > 100_000) {
      errors[field] = "Enter a whole number from 0 to 100000.";
    } else {
      parsed[field] = value;
    }
  }
  if (!errors.available_beds && !errors.total_beds && parsed.available_beds > parsed.total_beds) {
    errors.available_beds = "Free beds cannot exceed total beds.";
  }
  if (!errors.icu_available && !errors.icu_total && parsed.icu_available > parsed.icu_total) {
    errors.icu_available = "Free ICU beds cannot exceed total ICU beds.";
  }
  if (values.note.length > 500) errors.note = "The note is at most 500 characters.";
  if (Object.keys(errors).length > 0) return { errors, input: null };

  const input: HospitalCapacityInput = {};
  for (const field of fields) {
    if (parsed[field] !== hospital[field]) input[field] = parsed[field];
  }
  if (values.accepting_emergencies !== hospital.accepting_emergencies) {
    input.accepting_emergencies = values.accepting_emergencies;
  }
  const specialties = parseCapabilities(values.specialties);
  if (JSON.stringify(specialties) !== JSON.stringify(hospital.specialties)) {
    input.specialties = specialties;
  }
  if (values.note.trim()) input.note = values.note.trim();

  return { errors, input };
}

/** True when the report changes nothing (a note alone does not count). */
export function isEmptyUpdate(input: HospitalCapacityInput): boolean {
  return Object.keys(input).filter((key) => key !== "note").length === 0;
}

export interface HospitalFormValues {
  code: string;
  name: string;
  latitude: string;
  longitude: string;
  address: string;
  contact_phone: string;
  total_beds: string;
  available_beds: string;
  icu_total: string;
  icu_available: string;
  specialties: string;
  managed_by_id: string;
}

export type HospitalFormErrors = Partial<Record<keyof HospitalFormValues, string>>;

export const EMPTY_HOSPITAL_FORM: HospitalFormValues = {
  code: "",
  name: "",
  latitude: "",
  longitude: "",
  address: "",
  contact_phone: "",
  total_beds: "0",
  available_beds: "0",
  icu_total: "0",
  icu_available: "0",
  specialties: "",
  managed_by_id: "",
};

function coordinate(text: string, limit: number): number {
  if (text.trim() === "") return Number.NaN;
  const value = Number(text);
  return Number.isFinite(value) && Math.abs(value) <= limit ? value : Number.NaN;
}

/** Typing-mistake checks for registering a hospital; the server stays authoritative. */
export function validateHospitalForm(values: HospitalFormValues): {
  errors: HospitalFormErrors;
  input: CreateHospitalInput | null;
} {
  const errors: HospitalFormErrors = {};
  if (values.code.trim().length < 2) errors.code = "Enter a code of at least 2 characters.";
  if (values.name.trim().length < 2) errors.name = "Enter a name of at least 2 characters.";
  const latitude = coordinate(values.latitude, 90);
  const longitude = coordinate(values.longitude, 180);
  if (Number.isNaN(latitude)) errors.latitude = "Latitude must be a number between -90 and 90.";
  if (Number.isNaN(longitude)) errors.longitude = "Longitude must be a number between -180 and 180.";

  const fields = ["total_beds", "available_beds", "icu_total", "icu_available"] as const;
  const parsed = {} as Record<(typeof fields)[number], number>;
  for (const field of fields) {
    const value = count(values[field]);
    if (Number.isNaN(value) || value > 100_000) errors[field] = "Enter a whole number from 0 to 100000.";
    else parsed[field] = value;
  }
  if (!errors.available_beds && !errors.total_beds && parsed.available_beds > parsed.total_beds) {
    errors.available_beds = "Free beds cannot exceed total beds.";
  }
  if (!errors.icu_available && !errors.icu_total && parsed.icu_available > parsed.icu_total) {
    errors.icu_available = "Free ICU beds cannot exceed total ICU beds.";
  }
  if (Object.keys(errors).length > 0) return { errors, input: null };

  return {
    errors,
    input: {
      code: values.code.trim(),
      name: values.name.trim(),
      latitude,
      longitude,
      address: values.address.trim() || null,
      contact_phone: values.contact_phone.trim() || null,
      ...parsed,
      specialties: parseCapabilities(values.specialties),
      managed_by_id: values.managed_by_id || null,
    },
  };
}
