import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type Hospital } from "@raksha/api-client";

import { HospitalDetail } from "@/components/hospitals/HospitalDetail";
import { HospitalEditForm } from "@/components/hospitals/HospitalEditForm";
import { buildDetailsUpdate, detailsFormFrom } from "@/lib/hospital";

const client = {
  updateHospital: vi.fn(),
  adminUsers: vi.fn(),
  hospitalNotices: vi.fn(),
  updateHospitalCapacity: vi.fn(),
};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));

function hospital(overrides: Partial<Hospital> = {}): Hospital {
  return {
    id: "h1",
    code: "GH-01",
    name: "General Hospital",
    latitude: "13.082700",
    longitude: "80.270700",
    address: "Park Town",
    contact_phone: "+91 44 2530 5000",
    total_beds: 100,
    available_beds: 12,
    icu_total: 20,
    icu_available: 3,
    accepting_emergencies: true,
    specialties: ["trauma"],
    is_active: true,
    managed_by: { id: "op1", full_name: "Asha Operator", role: "HOSPITAL_OPERATOR" },
    capacity_updated_at: new Date().toISOString(),
    created_at: "",
    updated_at: "",
    ...overrides,
  } as Hospital;
}

beforeEach(() => {
  for (const fn of Object.values(client)) fn.mockReset();
  client.adminUsers.mockResolvedValue({
    items: [
      { id: "op1", full_name: "Asha Operator", email: "asha@example.com" },
      { id: "op2", full_name: "Ravi Operator", email: "ravi@example.com" },
    ],
  });
  client.hospitalNotices.mockResolvedValue([]);
  client.updateHospital.mockImplementation(async (_id: string, input: object) => ({ ...hospital(), ...input }));
});

describe("buildDetailsUpdate", () => {
  const base = hospital();

  it("sends nothing when nothing changed", () => {
    const { errors, input } = buildDetailsUpdate(base, detailsFormFrom(base));
    expect(errors).toEqual({});
    expect(input).toEqual({});
  });

  it("sends only the fields that changed, so an untouched phone number is never rewritten", () => {
    const form = { ...detailsFormFrom(base), name: "  Government General  ", address: "" };
    expect(buildDetailsUpdate(base, form).input).toEqual({ name: "Government General", address: null });
  });

  it("moves a hospital with latitude and longitude together, even if only one was edited", () => {
    const form = { ...detailsFormFrom(base), latitude: "19.076" };
    expect(buildDetailsUpdate(base, form).input).toEqual({ latitude: 19.076, longitude: 80.2707 });
  });

  it("links, changes and unlinks the operator", () => {
    expect(buildDetailsUpdate(base, { ...detailsFormFrom(base), managed_by_id: "op2" }).input).toEqual({ managed_by_id: "op2" });
    expect(buildDetailsUpdate(base, { ...detailsFormFrom(base), managed_by_id: "" }).input).toEqual({ managed_by_id: null });
  });

  it("catches typing mistakes before a round trip", () => {
    const form = { ...detailsFormFrom(base), name: "x", latitude: "ninety", longitude: "181" };
    const { errors, input } = buildDetailsUpdate(base, form);
    expect(input).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["latitude", "longitude", "name"]);
  });
});

describe("HospitalEditForm", () => {
  it("saves a correction and reports the server's record", async () => {
    const onSaved = vi.fn();
    render(<HospitalEditForm hospital={hospital()} onSaved={onSaved} onCancel={() => {}} />);
    const name = screen.getByLabelText(/^Name/);
    await userEvent.clear(name);
    await userEvent.type(name, "Government General");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(client.updateHospital).toHaveBeenCalledWith("h1", { name: "Government General" }));
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ name: "Government General" }));
  });

  it("says so, and does not call the server, when nothing has changed", async () => {
    render(<HospitalEditForm hospital={hospital()} onSaved={() => {}} onCancel={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Nothing has changed.")).toBeInTheDocument();
    expect(client.updateHospital).not.toHaveBeenCalled();
  });

  it("states that the code and the capacity are not edited here", () => {
    render(<HospitalEditForm hospital={hospital()} onSaved={() => {}} onCancel={() => {}} />);
    expect(screen.getByText(/cannot be changed/)).toHaveTextContent("GH-01");
    expect(screen.queryByLabelText(/beds/i)).toBeNull();
  });

  it("keeps a no-longer-listed operator selectable instead of silently unlinking them", async () => {
    client.adminUsers.mockResolvedValue({ items: [{ id: "op2", full_name: "Ravi Operator", email: "ravi@example.com" }] });
    render(<HospitalEditForm hospital={hospital()} onSaved={() => {}} onCancel={() => {}} />);
    const select = await screen.findByLabelText("Hospital operator");
    await waitFor(() => expect(select).toHaveValue("op1"));
    expect(screen.getByRole("option", { name: /Asha Operator/ })).toBeInTheDocument();
  });

  it("asks twice before retiring, and shows the server's reason when it refuses", async () => {
    client.updateHospital.mockRejectedValue(
      new ApiError(409, { code: "HOSPITAL_HAS_OPEN_NOTICES", message: "This hospital still has open inbound-patient notices." }),
    );
    render(<HospitalEditForm hospital={hospital()} onSaved={() => {}} onCancel={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /Retire this hospital/ }));
    expect(client.updateHospital).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm retire" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/open inbound-patient notices/);
    expect(client.updateHospital).toHaveBeenCalledWith("h1", { is_active: false });
    expect(screen.getByRole("button", { name: /Retire this hospital/ })).toBeInTheDocument();
  });

  it("offers to restore a retired hospital", async () => {
    render(<HospitalEditForm hospital={hospital({ is_active: false })} onSaved={() => {}} onCancel={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Restore this hospital" }));
    await waitFor(() => expect(client.updateHospital).toHaveBeenCalledWith("h1", { is_active: true }));
  });
});

describe("HospitalDetail", () => {
  const props = { canSeeNotices: false, canReportCapacity: false, noticeViewer: "dispatch" as const, onChanged: () => {} };

  it("offers Edit details to administrators only", () => {
    const { rerender } = render(<HospitalDetail hospital={hospital()} {...props} />);
    expect(screen.queryByRole("button", { name: "Edit details" })).toBeNull();
    rerender(<HospitalDetail hospital={hospital()} {...props} canEditDetails />);
    expect(screen.getByRole("button", { name: "Edit details" })).toBeInTheDocument();
  });

  it("opens the form, and marks a retired hospital as retired", async () => {
    render(<HospitalDetail hospital={hospital({ is_active: false })} {...props} canEditDetails />);
    expect(screen.getByText("Retired")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit details" }));
    expect(screen.getByRole("form", { name: "Edit hospital details" })).toBeInTheDocument();
  });
});
