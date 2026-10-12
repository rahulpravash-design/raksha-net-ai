import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type Hospital, type HospitalNotice } from "@raksha/api-client";

import { CapacityForm } from "@/components/hospitals/CapacityForm";
import { HospitalCard } from "@/components/hospitals/HospitalCard";
import { HospitalDetail } from "@/components/hospitals/HospitalDetail";
import { HospitalNoticePanel } from "@/components/hospitals/HospitalNoticePanel";
import { NoticeList } from "@/components/hospitals/NoticeList";
import { NotifyHospital } from "@/components/hospitals/NotifyHospital";

const client = {
  updateHospitalCapacity: vi.fn(),
  hospitalNotices: vi.fn(),
  incidentHospitalNotices: vi.fn(),
  hospitals: vi.fn(),
  hospitalsNearby: vi.fn(),
  createHospitalNotice: vi.fn(),
  respondToHospitalNotice: vi.fn(),
};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));

function hospital(overrides: Partial<Hospital> = {}): Hospital {
  return {
    id: "h1",
    code: "GH-01",
    name: "General Hospital",
    latitude: "13.08",
    longitude: "80.27",
    address: null,
    contact_phone: null,
    total_beds: 100,
    available_beds: 12,
    icu_total: 20,
    icu_available: 3,
    accepting_emergencies: true,
    specialties: ["trauma"],
    is_active: true,
    managed_by: null,
    capacity_updated_at: new Date().toISOString(),
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

function notice(overrides: Partial<HospitalNotice> = {}): HospitalNotice {
  return {
    id: "n1",
    hospital_id: "h1",
    incident_id: "inc-1",
    dispatch_id: null,
    status: "NOTIFIED",
    patient_count: 3,
    category: "FIRE",
    severity: "CRITICAL",
    eta_minutes: 8,
    clinical_notes: "Smoke inhalation",
    response_note: null,
    created_by: { id: "u", full_name: "Dana Dispatcher", role: "DISPATCHER" },
    acknowledged_at: null,
    closed_at: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

beforeEach(() => {
  for (const fn of Object.values(client)) fn.mockReset();
  client.hospitalNotices.mockResolvedValue([]);
  client.incidentHospitalNotices.mockResolvedValue([]);
  client.hospitals.mockResolvedValue({ items: [hospital()], total: 1 });
  client.respondToHospitalNotice.mockResolvedValue(notice());
  client.updateHospitalCapacity.mockResolvedValue(hospital());
});

describe("HospitalCard", () => {
  it("states capacity in words and warns when the figures are old", () => {
    const old = new Date(Date.now() - 9 * 3_600_000).toISOString();
    render(<ul><HospitalCard hospital={hospital({ capacity_updated_at: old })} selected={false} mine={false} index={0} onSelect={() => {}} /></ul>);
    expect(screen.getAllByText(/beds free/).map((el) => el.textContent?.replace(/\s+/g, " "))).toContain("12 of 100 beds free");
    expect(screen.getByText(/may be out of date/i)).toBeInTheDocument();
  });

  it("says plainly when a hospital has never reported", () => {
    render(<ul><HospitalCard hospital={hospital({ capacity_updated_at: null })} selected={false} mine={true} index={0} onSelect={() => {}} /></ul>);
    expect(screen.getByText(/capacity never reported/i)).toBeInTheDocument();
    expect(screen.getByText(/your hospital/i)).toBeInTheDocument();
  });

  it("marks a hospital that is not accepting with a word, not colour alone", () => {
    render(<ul><HospitalCard hospital={hospital({ accepting_emergencies: false })} selected={false} mine={false} index={0} onSelect={() => {}} /></ul>);
    expect(screen.getByText("Not accepting")).toBeInTheDocument();
  });
});

describe("CapacityForm", () => {
  it("sends only the changes", async () => {
    const onSaved = vi.fn();
    render(<CapacityForm hospital={hospital()} onSaved={onSaved} onCancel={() => {}} />);
    const free = screen.getByLabelText("Free beds");
    await userEvent.clear(free);
    await userEvent.type(free, "7");
    await userEvent.click(screen.getByRole("button", { name: /report capacity/i }));

    await waitFor(() => expect(client.updateHospitalCapacity).toHaveBeenCalledWith("h1", { available_beds: 7 }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("blocks free beds above the total without calling the API", async () => {
    render(<CapacityForm hospital={hospital()} onSaved={() => {}} onCancel={() => {}} />);
    const free = screen.getByLabelText("Free beds");
    await userEvent.clear(free);
    await userEvent.type(free, "500");
    await userEvent.click(screen.getByRole("button", { name: /report capacity/i }));
    expect(await screen.findByText(/cannot exceed total beds/i)).toBeInTheDocument();
    expect(client.updateHospitalCapacity).not.toHaveBeenCalled();
  });

  it("does not send an empty report", async () => {
    render(<CapacityForm hospital={hospital()} onSaved={() => {}} onCancel={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /report capacity/i }));
    expect(await screen.findByText(/nothing has changed/i)).toBeInTheDocument();
    expect(client.updateHospitalCapacity).not.toHaveBeenCalled();
  });

  it("shows the server's refusal", async () => {
    client.updateHospitalCapacity.mockRejectedValue(
      new ApiError(403, { code: "FORBIDDEN", message: "You do not maintain this hospital's capacity." }),
    );
    render(<CapacityForm hospital={hospital()} onSaved={() => {}} onCancel={() => {}} />);
    await userEvent.click(screen.getByLabelText(/accepting emergency/i));
    await userEvent.click(screen.getByRole("button", { name: /report capacity/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/do not maintain/i);
  });
});

describe("NoticeList actions by viewer", () => {
  it("lets the hospital acknowledge or divert, but not withdraw", () => {
    render(<NoticeList notices={[notice()]} viewer="hospital" onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: "Acknowledge" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /divert/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /withdraw/i })).toBeNull();
  });

  it("lets a dispatcher only withdraw — never acknowledge on the hospital's behalf", () => {
    render(<NoticeList notices={[notice()]} viewer="dispatch" onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: /withdraw notice/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Acknowledge" })).toBeNull();
    expect(screen.queryByRole("button", { name: /divert/i })).toBeNull();
  });

  it("acknowledges in one click", async () => {
    const onChanged = vi.fn();
    render(<NoticeList notices={[notice()]} viewer="hospital" onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(client.respondToHospitalNotice).toHaveBeenCalledWith("n1", "ACKNOWLEDGED", undefined));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("requires a reason to divert", async () => {
    render(<NoticeList notices={[notice()]} viewer="hospital" onChanged={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /divert…/i }));
    const confirm = screen.getByRole("button", { name: /confirm divert/i });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/reason for diverting/i), "No trauma bay free");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => expect(client.respondToHospitalNotice).toHaveBeenCalledWith("n1", "DIVERTED", "No trauma bay free"));
  });

  it("offers nothing on a closed notice, and shows what the hospital said", () => {
    render(
      <NoticeList notices={[notice({ status: "DIVERTED", response_note: "Full" })]} viewer="hospital" onChanged={() => {}} />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/hospital response: full/i)).toBeInTheDocument();
  });

  it("shows a refused transition", async () => {
    client.respondToHospitalNotice.mockRejectedValue(
      new ApiError(409, { code: "NOTICE_INVALID_TRANSITION", message: "A notice cannot move from ARRIVED to CANCELLED." }),
    );
    render(<NoticeList notices={[notice()]} viewer="hospital" onChanged={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot move/i);
  });
});

describe("HospitalDetail", () => {
  it("does not request notices for a viewer who may not see them", async () => {
    render(
      <HospitalDetail hospital={hospital()} canSeeNotices={false} canReportCapacity={false} noticeViewer="hospital" onChanged={() => {}} />,
    );
    expect(screen.getByText(/visible to this hospital's own operators and to dispatchers/i)).toBeInTheDocument();
    expect(client.hospitalNotices).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /report capacity/i })).toBeNull();
  });

  it("lists inbound patients and says what a notice never contains", async () => {
    client.hospitalNotices.mockResolvedValue([notice()]);
    render(
      <HospitalDetail hospital={hospital()} canSeeNotices={true} canReportCapacity={true} noticeViewer="hospital" onChanged={() => {}} />,
    );
    expect(await screen.findByText(/3 patients/)).toBeInTheDocument();
    expect(screen.getByText(/never carries the reporter/i)).toBeInTheDocument();
  });
});

const incident = { id: "inc-1", latitude: "13.08", longitude: "80.27", people_affected: 2, severity: null };

describe("NotifyHospital", () => {
  const near = {
    id: "h1", code: "GH-01", name: "General Hospital", latitude: 13.1, longitude: 80.3,
    available_beds: 5, icu_available: 1, accepting_emergencies: true, specialties: ["trauma"],
    contact_phone: null, distance_km: 2.3,
  };

  beforeEach(() => {
    client.hospitalsNearby.mockResolvedValue({ items: [near], count: 1 });
    client.createHospitalNotice.mockResolvedValue(notice());
  });

  it("sends nothing until the final confirmation, then sends the minimal payload", async () => {
    const onSent = vi.fn();
    render(<NotifyHospital incident={incident} onSent={onSent} onCancel={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Choose" }));
    await userEvent.type(screen.getByLabelText(/^ETA \(minutes\)/), "10");
    await userEvent.type(screen.getByLabelText(/clinical notes/i), "Two burns");
    await userEvent.click(screen.getByRole("button", { name: /review notice/i }));

    expect(client.createHospitalNotice).not.toHaveBeenCalled();
    expect(screen.getByText(/will not include the reporter, contact details, report text or location/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /send notice/i }));

    await waitFor(() =>
      expect(client.createHospitalNotice).toHaveBeenCalledWith("inc-1", {
        hospital_id: "h1",
        patient_count: 2,
        severity: null,
        eta_minutes: 10,
        clinical_notes: "Two burns",
      }),
    );
    await waitFor(() => expect(onSent).toHaveBeenCalled());
  });

  it("validates the patient count and ETA before the review step", async () => {
    render(<NotifyHospital incident={incident} onSent={() => {}} onCancel={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Choose" }));
    const patients = screen.getByLabelText("Patients");
    await userEvent.clear(patients);
    await userEvent.type(patients, "0");
    await userEvent.type(screen.getByLabelText(/^ETA \(minutes\)/), "abc");
    await userEvent.click(screen.getByRole("button", { name: /review notice/i }));
    expect(await screen.findByText(/whole number from 1 to 1000/i)).toBeInTheDocument();
    expect(screen.getByText(/whole minutes/i)).toBeInTheDocument();
  });

  it("explains an empty result instead of showing nothing", async () => {
    client.hospitalsNearby.mockResolvedValue({ items: [], count: 0 });
    render(<NotifyHospital incident={incident} onSent={() => {}} onCancel={() => {}} />);
    expect(await screen.findByText(/no hospital within 20 km is accepting/i)).toBeInTheDocument();
  });

  it("returns to the form and shows the server's message if sending fails", async () => {
    client.createHospitalNotice.mockRejectedValue(
      new ApiError(404, { code: "NOT_FOUND", message: "Hospital not found." }),
    );
    render(<NotifyHospital incident={incident} onSent={() => {}} onCancel={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Choose" }));
    await userEvent.click(screen.getByRole("button", { name: /review notice/i }));
    await userEvent.click(screen.getByRole("button", { name: /send notice/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/hospital not found/i);
    expect(screen.getByRole("button", { name: /review notice/i })).toBeInTheDocument();
  });
});

describe("HospitalNoticePanel", () => {
  it("names the hospitals notified and offers notifying only to dispatchers on an open incident", async () => {
    client.incidentHospitalNotices.mockResolvedValue([notice()]);
    const { unmount } = render(<HospitalNoticePanel incident={incident} incidentOpen={true} canDispatch={true} />);
    expect(await screen.findByText(/General Hospital was notified/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /notify a hospital/i })).toBeInTheDocument();
    unmount();

    render(<HospitalNoticePanel incident={incident} incidentOpen={true} canDispatch={false} />);
    await screen.findByText(/only dispatchers and administrators/i);
    expect(screen.queryByRole("button", { name: /notify a hospital/i })).toBeNull();
  });

  it("offers nothing on a closed incident", async () => {
    render(<HospitalNoticePanel incident={incident} incidentOpen={false} canDispatch={true} />);
    expect(await screen.findByText(/no further notices can be sent/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /notify a hospital/i })).toBeNull();
  });
});
