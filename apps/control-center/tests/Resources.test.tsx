import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type Resource } from "@raksha/api-client";

import { ResourceDetail } from "@/components/resources/ResourceDetail";
import { ResourceForm } from "@/components/resources/ResourceForm";
import { ResourceStatsBar } from "@/components/resources/ResourceStatsBar";
import { EMPTY_RESOURCE_FORM } from "@/lib/resourceForm";

const setResourceStatus = vi.fn();
const updateResource = vi.fn();
const responderDirectory = vi.fn();
const client = { setResourceStatus, updateResource, responderDirectory };
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));

function unit(overrides: Partial<Resource> = {}): Resource {
  return {
    id: "r1",
    call_sign: "AMB-1",
    name: "Ambulance One",
    resource_type: "AMBULANCE",
    status: "AVAILABLE",
    latitude: "13.0800000",
    longitude: "80.2700000",
    base_address: "Station 4",
    capabilities: ["als"],
    crew_size: 2,
    contact_phone: null,
    is_active: true,
    operator: null,
    status_changed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  responderDirectory.mockReset().mockResolvedValue([{ id: "r-1", full_name: "Crew One", role: "RESPONDER" }]);
  setResourceStatus.mockReset().mockResolvedValue(unit({ status: "OUT_OF_SERVICE" }));
  updateResource.mockReset().mockResolvedValue(unit());
});

describe("ResourceDetail", () => {
  it("offers read-only access to roles that cannot manage", () => {
    render(<ResourceDetail resource={unit()} canManage={false} onChanged={vi.fn()} />);
    expect(screen.getByText("Station 4")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit|deactivate|set /i })).toBeNull();
    expect(screen.getByText(/can view the inventory but not change it/i)).toBeInTheDocument();
  });

  it("sets a unit out of service and reports the change", async () => {
    const onChanged = vi.fn();
    render(<ResourceDetail resource={unit()} canManage={true} onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("button", { name: /set out of service/i }));

    await waitFor(() => expect(setResourceStatus).toHaveBeenCalledWith("r1", "OUT_OF_SERVICE"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("does not let a committed unit be set available by hand", () => {
    render(
      <ResourceDetail resource={unit({ status: "EN_ROUTE" })} canManage={true} onChanged={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: /set available/i })).toBeNull();
    expect(screen.getByText(/committed to an incident/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /deactivate/i })).toBeDisabled();
  });

  it("deactivates only after an explicit second step", async () => {
    render(<ResourceDetail resource={unit()} canManage={true} onChanged={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /deactivate…/i }));
    expect(updateResource).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /confirm deactivate/i }));
    await waitFor(() => expect(updateResource).toHaveBeenCalledWith("r1", { is_active: false }));
  });

  it("saves only the fields that changed", async () => {
    render(<ResourceDetail resource={unit()} canManage={true} onChanged={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /edit details/i }));
    const name = screen.getByLabelText(/^name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Ambulance Uno");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(updateResource).toHaveBeenCalledWith("r1", { name: "Ambulance Uno" }));
  });

  it("shows the server's message when a change is refused", async () => {
    setResourceStatus.mockRejectedValue(
      new ApiError(403, { code: "FORBIDDEN", message: "You do not have permission." }),
    );
    render(<ResourceDetail resource={unit()} canManage={true} onChanged={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /set out of service/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/do not have permission/i);
  });

  it("marks a deactivated unit as never suggested", () => {
    render(<ResourceDetail resource={unit({ is_active: false })} canManage={true} onChanged={vi.fn()} />);
    expect(screen.getByText(/never suggested for dispatch/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reactivate/i })).toBeInTheDocument();
  });
});

describe("ResourceForm", () => {
  it("blocks submission and flags the fields when input is invalid", async () => {
    const onSubmit = vi.fn();
    render(
      <ResourceForm mode="create" initial={EMPTY_RESOURCE_FORM} onSubmit={onSubmit} onCancel={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /register resource/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText(/latitude must be a number/i)).toBeInTheDocument();
    expect(screen.getByText(/call sign of at least 2/i)).toBeInTheDocument();
  });

  it("submits a normalised payload and shows a server refusal", async () => {
    const onSubmit = vi.fn().mockResolvedValue("A resource with that call sign already exists.");
    render(
      <ResourceForm mode="create" initial={EMPTY_RESOURCE_FORM} onSubmit={onSubmit} onCancel={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText(/call sign/i), "amb-9");
    await userEvent.type(screen.getByLabelText(/^name/i), "Ambulance Nine");
    await userEvent.type(screen.getByLabelText(/latitude/i), "13.1");
    await userEvent.type(screen.getByLabelText(/longitude/i), "80.2");
    await userEvent.type(screen.getByLabelText(/capabilities/i), "ALS, oxygen");
    await userEvent.click(screen.getByRole("button", { name: /register resource/i }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ call_sign: "amb-9", latitude: 13.1, capabilities: ["als", "oxygen"] }),
      ),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/call sign already exists/i);
  });
});

describe("ResourceForm crew picker", () => {
  it("offers active responders and sends the chosen one", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);
    render(<ResourceForm mode="create" initial={EMPTY_RESOURCE_FORM} onSubmit={onSubmit} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/call sign/i), "amb-7");
    await userEvent.type(screen.getByLabelText(/^name/i), "Ambulance Seven");
    await userEvent.type(screen.getByLabelText(/latitude/i), "13.1");
    await userEvent.type(screen.getByLabelText(/longitude/i), "80.2");
    await userEvent.selectOptions(await screen.findByLabelText("Crew member"), "r-1");
    await userEvent.click(screen.getByRole("button", { name: /register resource/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ operator_id: "r-1" })));
  });

  it("still works when the directory cannot be loaded", async () => {
    responderDirectory.mockRejectedValue(new Error("down"));
    render(<ResourceForm mode="create" initial={EMPTY_RESOURCE_FORM} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByLabelText("Crew member")).toHaveValue("");
  });
});

describe("ResourceStatsBar", () => {
  it("shows the API's counts without recomputing them", () => {
    render(
      <ResourceStatsBar
        stats={{ total_active: 7, by_status: { AVAILABLE: 4, DISPATCHED: 3 }, by_type: { AMBULANCE: 5, RESCUE_TEAM: 2 } }}
      />,
    );
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText(/Ambulance 5 · Rescue team 2/)).toBeInTheDocument();
  });

  it("does not invent numbers before data arrives", () => {
    render(<ResourceStatsBar stats={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
