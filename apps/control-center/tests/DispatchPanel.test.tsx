import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@raksha/api-client";
import type {
  Dispatch,
  ResourceRecommendation,
  ResourceRecommendations,
} from "@raksha/api-client";

import { DispatchPanel } from "@/components/DispatchPanel";

const resourceRecommendations = vi.fn();
const incidentDispatches = vi.fn();
const dispatchResource = vi.fn();
const setDispatchStatus = vi.fn();

// One stable client: the panel re-runs its load effect if the client changes.
const client = {
  resourceRecommendations,
  incidentDispatches,
  dispatchResource,
  setDispatchStatus,
};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));

function recommendation(
  callSign: string,
  rank: number,
  reasons: string[] = ["Closest available unit"],
): ResourceRecommendation {
  return {
    resource: {
      id: `res-${callSign}`,
      call_sign: callSign,
      name: `Unit ${callSign}`,
      resource_type: "AMBULANCE",
      status: "AVAILABLE",
      latitude: 28.6,
      longitude: 77.2,
      capabilities: [],
      crew_size: 2,
      distance_km: 2.4,
    },
    rank,
    type_match: true,
    matched_capabilities: [],
    estimated_minutes: 6,
    reasons,
  };
}

function ranked(items: ResourceRecommendation[]): ResourceRecommendations {
  return { incident_id: "inc-1", searched_radius_km: 5, items, note: null };
}

function dispatchRow(overrides: Partial<Dispatch> = {}): Dispatch {
  return {
    id: "disp-1",
    incident_id: "inc-1",
    resource_id: "res-A1",
    status: "DISPATCHED",
    distance_km: 2.4,
    estimated_minutes: 6,
    note: null,
    cancel_reason: null,
    approved_by: { id: "u-1", full_name: "Dana Dispatcher", role: "DISPATCHER" },
    resource: {
      id: "res-A1",
      call_sign: "A1",
      name: "Unit A1",
      resource_type: "AMBULANCE",
      status: "DISPATCHED",
      latitude: "28.6",
      longitude: "77.2",
      base_address: null,
      capabilities: [],
      crew_size: 2,
      contact_phone: null,
      is_active: true,
      operator: null,
      status_changed_at: null,
      created_at: "2026-01-01T09:00:00Z",
      updated_at: "2026-01-01T09:00:00Z",
    },
    acknowledged_at: null,
    en_route_at: null,
    on_scene_at: null,
    closed_at: null,
    created_at: "2026-01-01T09:05:00Z",
    updated_at: "2026-01-01T09:05:00Z",
    ...overrides,
  };
}

function renderPanel(props: Partial<Parameters<typeof DispatchPanel>[0]> = {}) {
  const onChanged = vi.fn();
  render(
    <DispatchPanel
      incidentId="inc-1"
      incidentOpen={true}
      canDispatch={true}
      onChanged={onChanged}
      {...props}
    />,
  );
  return { onChanged };
}

beforeEach(() => {
  resourceRecommendations.mockReset().mockResolvedValue(ranked([]));
  incidentDispatches.mockReset().mockResolvedValue([]);
  dispatchResource.mockReset();
  setDispatchStatus.mockReset();
});

describe("DispatchPanel — recommendations", () => {
  it("shows ranked units with their reasons and an honest ETA label", async () => {
    resourceRecommendations.mockResolvedValue(
      ranked([
        recommendation("A1", 1, ["Closest available unit", "Type matches"]),
        recommendation("A2", 2),
      ]),
    );
    renderPanel();

    const list = await screen.findByRole("list", { name: /suggested units/i });
    expect(within(list).getByText(/A1 · Unit A1/)).toBeInTheDocument();
    expect(within(list).getByText("Type matches")).toBeInTheDocument();
    expect(within(list).getAllByText(/straight-line estimate/i)).toHaveLength(2);
    expect(screen.getByText(/does not change the incident/i)).toBeInTheDocument();
  });

  it("says so when nothing is available nearby", async () => {
    renderPanel();
    expect(await screen.findByText(/no available unit was found/i)).toBeInTheDocument();
  });

  it("does not ask for recommendations when the user cannot dispatch", async () => {
    incidentDispatches.mockResolvedValue([dispatchRow()]);
    renderPanel({ canDispatch: false });

    expect(await screen.findByText(/approved by dana dispatcher/i)).toBeInTheDocument();
    expect(resourceRecommendations).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /dispatch…/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /stand down/i })).toBeNull();
    expect(screen.getByText(/only dispatchers and administrators/i)).toBeInTheDocument();
  });

  it("offers no dispatching on a closed incident", async () => {
    renderPanel({ incidentOpen: false });

    expect(await screen.findByText(/incident is closed/i)).toBeInTheDocument();
    expect(resourceRecommendations).not.toHaveBeenCalled();
  });
});

describe("DispatchPanel — confirm to dispatch", () => {
  beforeEach(() => {
    resourceRecommendations.mockResolvedValue(ranked([recommendation("A1", 1)]));
  });

  it("sends nothing on the first click, and nothing names an approver", async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: /dispatch…/i }));

    expect(dispatchResource).not.toHaveBeenCalled();
    expect(
      screen.getByText(/you will be recorded as the approving dispatcher/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/approv/i)).toBeNull();
  });

  it("dispatches on the explicit second step, with the optional note", async () => {
    dispatchResource.mockResolvedValue(dispatchRow());
    const { onChanged } = renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: /dispatch…/i }));
    await userEvent.type(screen.getByLabelText(/note for the crew/i), "Use north gate");
    await userEvent.click(screen.getByRole("button", { name: /confirm dispatch/i }));

    await waitFor(() =>
      expect(dispatchResource).toHaveBeenCalledWith("inc-1", "res-A1", "Use north gate"),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("can be backed out of without dispatching", async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: /dispatch…/i }));
    await userEvent.click(screen.getByRole("button", { name: /not now/i }));

    expect(dispatchResource).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /confirm dispatch/i })).toBeNull();
  });

  it("shows the server's reason and refreshes the ranking when a unit was taken", async () => {
    dispatchResource.mockRejectedValue(
      new ApiError(409, {
        code: "RESOURCE_ALREADY_DISPATCHED",
        message: "That unit is already committed to another incident.",
      }),
    );
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: /dispatch…/i }));
    const calls = resourceRecommendations.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /confirm dispatch/i }));

    expect(await screen.findByText(/already committed/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(resourceRecommendations.mock.calls.length).toBeGreaterThan(calls),
    );
    expect(screen.queryByRole("button", { name: /confirm dispatch/i })).toBeNull();
  });
});

describe("DispatchPanel — existing dispatches and stand down", () => {
  it("lists who approved each dispatch, and why a unit was stood down", async () => {
    incidentDispatches.mockResolvedValue([
      dispatchRow({
        id: "d2",
        status: "CANCELLED",
        cancel_reason: "Reassigned to a larger incident",
      }),
    ]);
    renderPanel();

    expect(await screen.findByText(/approved by dana dispatcher/i)).toBeInTheDocument();
    expect(screen.getByText(/reassigned to a larger incident/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /stand down/i })).toBeNull();
  });

  it("will not stand a unit down without a reason", async () => {
    incidentDispatches.mockResolvedValue([dispatchRow()]);
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: /stand down…/i }));

    expect(screen.getByRole("button", { name: /confirm stand down/i })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/reason/i), "   ");
    expect(screen.getByRole("button", { name: /confirm stand down/i })).toBeDisabled();
  });

  it("cancels the dispatch with the reason", async () => {
    incidentDispatches.mockResolvedValue([dispatchRow()]);
    setDispatchStatus.mockResolvedValue({});
    const { onChanged } = renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: /stand down…/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "False alarm");
    await userEvent.click(screen.getByRole("button", { name: /confirm stand down/i }));

    await waitFor(() =>
      expect(setDispatchStatus).toHaveBeenCalledWith("disp-1", "CANCELLED", {
        reason: "False alarm",
      }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("shows a load failure instead of an empty panel", async () => {
    incidentDispatches.mockRejectedValue(
      new ApiError(503, { code: "SERVICE_BUSY", message: "The system is very busy." }),
    );
    renderPanel();
    expect(await screen.findByText(/very busy/i)).toBeInTheDocument();
  });
});
