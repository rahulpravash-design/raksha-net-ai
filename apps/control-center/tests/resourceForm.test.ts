import { describe, expect, it } from "vitest";

import type { Resource } from "@raksha/api-client";

import {
  EMPTY_RESOURCE_FORM,
  changesFrom,
  formFromResource,
  parseCapabilities,
  validateResourceForm,
} from "@/lib/resourceForm";

const valid = {
  ...EMPTY_RESOURCE_FORM,
  call_sign: "amb-1",
  name: "Ambulance One",
  latitude: "13.08",
  longitude: "80.27",
};

const resource = {
  id: "r1",
  call_sign: "AMB-1",
  name: "Ambulance One",
  resource_type: "AMBULANCE",
  status: "AVAILABLE",
  latitude: "13.0800000",
  longitude: "80.2700000",
  base_address: null,
  capabilities: ["als"],
  crew_size: 2,
  contact_phone: null,
  is_active: true,
  operator: null,
  status_changed_at: null,
  created_at: "",
  updated_at: "",
} as Resource;

describe("parseCapabilities", () => {
  it("trims, lower-cases and de-duplicates", () => {
    expect(parseCapabilities(" ALS, oxygen,  als ,, ")).toEqual(["als", "oxygen"]);
    expect(parseCapabilities("")).toEqual([]);
  });
});

describe("validateResourceForm", () => {
  it("accepts a complete form and normalises it", () => {
    const { errors, input } = validateResourceForm(
      { ...valid, capabilities: "ALS, Oxygen", crew_size: "3" },
      "create",
    );
    expect(errors).toEqual({});
    expect(input).toMatchObject({
      call_sign: "amb-1",
      latitude: 13.08,
      capabilities: ["als", "oxygen"],
      crew_size: 3,
      base_address: null,
    });
  });

  it("reports each problem against its field", () => {
    const { errors, input } = validateResourceForm(
      { ...valid, call_sign: "a", name: "", latitude: "91", longitude: "abc", crew_size: "2.5" },
      "create",
    );
    expect(input).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["call_sign", "crew_size", "latitude", "longitude", "name"]);
  });

  it("does not require a call sign when editing (it cannot change)", () => {
    const { errors } = validateResourceForm({ ...valid, call_sign: "" }, "edit");
    expect(errors.call_sign).toBeUndefined();
  });

  it("treats empty coordinates as an error, not zero", () => {
    const { errors } = validateResourceForm({ ...valid, latitude: "", longitude: "" }, "create");
    expect(errors.latitude).toBeDefined();
    expect(errors.longitude).toBeDefined();
  });
});

describe("changesFrom", () => {
  it("is empty when nothing changed", () => {
    const { input } = validateResourceForm(formFromResource(resource), "edit");
    expect(changesFrom(resource, input!)).toEqual({});
  });

  it("sends only what changed, and the coordinate pair together", () => {
    const form = { ...formFromResource(resource), name: "Ambulance Uno", latitude: "13.1" };
    const { input } = validateResourceForm(form, "edit");
    expect(changesFrom(resource, input!)).toEqual({
      name: "Ambulance Uno",
      latitude: 13.1,
      longitude: 80.27,
    });
  });

  it("can clear an optional field", () => {
    const withPhone = { ...resource, contact_phone: "555" } as Resource;
    const { input } = validateResourceForm({ ...formFromResource(withPhone), contact_phone: "" }, "edit");
    expect(changesFrom(withPhone, input!)).toEqual({ contact_phone: null });
  });
});
