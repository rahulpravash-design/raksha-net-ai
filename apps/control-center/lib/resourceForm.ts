import type {
  CreateResourceInput,
  Resource,
  ResourceType,
  UpdateResourceInput,
} from "@raksha/api-client";

export interface ResourceFormValues {
  call_sign: string;
  name: string;
  resource_type: ResourceType;
  latitude: string;
  longitude: string;
  base_address: string;
  capabilities: string;
  crew_size: string;
  contact_phone: string;
  /** Empty means no crew member linked. */
  operator_id: string;
}

export type ResourceFormErrors = Partial<Record<keyof ResourceFormValues, string>>;

export const EMPTY_RESOURCE_FORM: ResourceFormValues = {
  call_sign: "",
  name: "",
  resource_type: "AMBULANCE",
  latitude: "",
  longitude: "",
  base_address: "",
  capabilities: "",
  crew_size: "",
  contact_phone: "",
  operator_id: "",
};

export function formFromResource(resource: Resource): ResourceFormValues {
  return {
    call_sign: resource.call_sign,
    name: resource.name,
    resource_type: resource.resource_type,
    latitude: String(Number(resource.latitude)),
    longitude: String(Number(resource.longitude)),
    base_address: resource.base_address ?? "",
    capabilities: resource.capabilities.join(", "),
    crew_size: resource.crew_size === null ? "" : String(resource.crew_size),
    contact_phone: resource.contact_phone ?? "",
    operator_id: resource.operator?.id ?? "",
  };
}

/** "als, oxygen,  ALS" -> ["als", "oxygen"]; the API lower-cases too. */
export function parseCapabilities(text: string): string[] {
  const seen = new Set<string>();
  for (const part of text.split(",")) {
    const value = part.trim().toLowerCase();
    if (value) seen.add(value);
  }
  return [...seen];
}

function parseNumber(text: string): number | null {
  if (text.trim() === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : Number.NaN;
}

/**
 * Client-side checks that catch typing mistakes before a round trip. The server
 * remains the authority (including that coordinates fall inside the deployment
 * area), and its message is shown if it disagrees.
 */
export function validateResourceForm(
  values: ResourceFormValues,
  mode: "create" | "edit",
): { errors: ResourceFormErrors; input: CreateResourceInput | null } {
  const errors: ResourceFormErrors = {};

  if (mode === "create") {
    const sign = values.call_sign.trim();
    if (sign.length < 2) errors.call_sign = "Enter a call sign of at least 2 characters.";
    else if (sign.length > 40) errors.call_sign = "Call sign is at most 40 characters.";
  }
  const name = values.name.trim();
  if (name.length < 2) errors.name = "Enter a name of at least 2 characters.";

  const latitude = parseNumber(values.latitude);
  const longitude = parseNumber(values.longitude);
  if (latitude === null || Number.isNaN(latitude) || latitude < -90 || latitude > 90) {
    errors.latitude = "Latitude must be a number between -90 and 90.";
  }
  if (longitude === null || Number.isNaN(longitude) || longitude < -180 || longitude > 180) {
    errors.longitude = "Longitude must be a number between -180 and 180.";
  }

  const crew = parseNumber(values.crew_size);
  if (crew !== null && (Number.isNaN(crew) || !Number.isInteger(crew) || crew < 0 || crew > 1000)) {
    errors.crew_size = "Crew size must be a whole number from 0 to 1000.";
  }

  const capabilities = parseCapabilities(values.capabilities);
  if (capabilities.length > 20) errors.capabilities = "At most 20 capabilities.";
  if (capabilities.some((c) => c.length > 40)) {
    errors.capabilities = "Each capability is at most 40 characters.";
  }

  if (Object.keys(errors).length > 0) return { errors, input: null };

  return {
    errors,
    input: {
      call_sign: values.call_sign.trim(),
      name,
      resource_type: values.resource_type,
      latitude: latitude as number,
      longitude: longitude as number,
      base_address: values.base_address.trim() || null,
      capabilities,
      crew_size: crew,
      contact_phone: values.contact_phone.trim() || null,
      operator_id: values.operator_id || null,
    },
  };
}

/** Only the fields that actually changed — the API treats absent as unchanged. */
export function changesFrom(resource: Resource, input: CreateResourceInput): UpdateResourceInput {
  const changes: UpdateResourceInput = {};
  if (input.name !== resource.name) changes.name = input.name;
  if (input.resource_type !== resource.resource_type) changes.resource_type = input.resource_type;
  if (
    input.latitude !== Number(resource.latitude) ||
    input.longitude !== Number(resource.longitude)
  ) {
    // The API requires the pair together.
    changes.latitude = input.latitude;
    changes.longitude = input.longitude;
  }
  if ((input.base_address ?? null) !== resource.base_address) changes.base_address = input.base_address ?? null;
  if (JSON.stringify(input.capabilities ?? []) !== JSON.stringify(resource.capabilities)) {
    changes.capabilities = input.capabilities ?? [];
  }
  if ((input.crew_size ?? null) !== resource.crew_size) changes.crew_size = input.crew_size ?? null;
  if ((input.contact_phone ?? null) !== resource.contact_phone) {
    changes.contact_phone = input.contact_phone ?? null;
  }
  if ((input.operator_id ?? null) !== (resource.operator?.id ?? null)) {
    changes.operator_id = input.operator_id ?? null;
  }
  return changes;
}
