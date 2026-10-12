import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BarList } from "@/components/analytics/BarList";
import { TimeStatsCard } from "@/components/analytics/TimeStatsCard";
import AnalyticsPage from "@/app/(console)/analytics/page";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
let currentUser: { id: string; role: string } | null = { id: "u1", role: "DISPATCHER" };
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ user: currentUser, loading: false }),
}));

const client = {
  responseTime: vi.fn(),
  resolutionTime: vi.fn(),
  categoryBreakdown: vi.fn(),
  resourceUtilization: vi.fn(),
  hotspots: vi.fn(),
};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));

const stats = (o = {}) => ({ sample_size: 12, avg_minutes: 8.6, median_minutes: 7, min_minutes: 2, max_minutes: 31, ...o });

beforeEach(() => {
  replace.mockReset();
  currentUser = { id: "u1", role: "DISPATCHER" };
  client.responseTime.mockReset().mockResolvedValue(stats());
  client.resolutionTime.mockReset().mockResolvedValue(stats({ median_minutes: 95, avg_minutes: 100, min_minutes: 20, max_minutes: 240 }));
  client.categoryBreakdown.mockReset().mockResolvedValue({
    total: 6,
    items: [
      { category: "FIRE", count: 4, avg_priority_score: 71.4 },
      { category: "FLOOD", count: 2, avg_priority_score: null },
    ],
  });
  client.resourceUtilization.mockReset().mockResolvedValue({
    period_start: null,
    period_end: null,
    items: [{ resource_type: "AMBULANCE", total_resources: 5, available_now: 3, dispatches_in_period: 4, avg_dispatches_per_resource: 0.8 }],
  });
  client.hotspots.mockReset().mockResolvedValue({
    cell_size_degrees: 0.01,
    items: [{ latitude: 13.08, longitude: 80.27, incident_count: 3 }],
  });
});

describe("TimeStatsCard", () => {
  it("leads with the median and always states the sample size", () => {
    render(<TimeStatsCard title="Time to first dispatch" description="d" stats={stats()} />);
    expect(screen.getByText("7 min")).toBeInTheDocument();
    expect(screen.getByText(/median, from 12 incidents/)).toBeInTheDocument();
    expect(screen.getByText("31 min")).toBeInTheDocument();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("warns when it rests on very few cases", () => {
    render(<TimeStatsCard title="t" description="d" stats={stats({ sample_size: 2 })} />);
    expect(screen.getByRole("note")).toHaveTextContent(/very few cases/i);
    expect(screen.getByText(/from 2 incidents/)).toBeInTheDocument();
  });

  it("says there is nothing to measure rather than showing zero", () => {
    render(
      <TimeStatsCard
        title="t"
        description="d"
        stats={{ sample_size: 0, avg_minutes: null, median_minutes: null, min_minutes: null, max_minutes: null }}
      />,
    );
    expect(screen.getByText(/nothing to measure/i)).toBeInTheDocument();
    expect(screen.queryByText(/under a minute/)).toBeNull();
  });
});

describe("BarList", () => {
  it("prints every value in text and scales bars to the largest row", () => {
    const { container } = render(
      <BarList label="x" rows={[
        { key: "a", label: "Fire", value: 4, valueLabel: "4" },
        { key: "b", label: "Flood", value: 2, valueLabel: "2", detail: "average 10" },
      ]} />,
    );
    expect(screen.getByText("Fire")).toBeInTheDocument();
    expect(screen.getByText("average 10")).toBeInTheDocument();
    const widths = [...container.querySelectorAll<HTMLElement>("[style]")].map((el) => el.style.width);
    expect(widths).toEqual(["100%", "50%"]);
  });
});

describe("AnalyticsPage", () => {
  it("shows all five measures, with coarsened hotspots and honest wording", async () => {
    render(<AnalyticsPage />);
    expect(await screen.findByRole("list", { name: "Incidents by category" })).toBeInTheDocument();
    expect(screen.getByText("1 h 35 min")).toBeInTheDocument();
    expect(screen.getByText(/3 of 5 available now · 0.8 per unit/)).toBeInTheDocument();
    const hotspots = screen.getByRole("region", { name: "Hotspots" });
    expect(within(hotspots).getByText(/about 1.1 km across/)).toBeInTheDocument();
    expect(within(hotspots).getByText(/never an individual report/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing here predicts future incidents/i)).toBeInTheDocument();
  });

  it("asks for the last seven days by default and re-queries on a new period", async () => {
    render(<AnalyticsPage />);
    await screen.findByRole("list", { name: "Incidents by category" });
    expect(client.responseTime.mock.calls[0]![0].since).toBeTypeOf("string");
    await userEvent.click(screen.getByRole("button", { name: "All time" }));
    await waitFor(() => expect(client.responseTime.mock.calls.at(-1)![0]).toEqual({}));
  });

  it("applies the category only where the API supports it", async () => {
    render(<AnalyticsPage />);
    await screen.findByRole("list", { name: "Incidents by category" });
    await userEvent.selectOptions(screen.getByLabelText("Filter by category"), "FIRE");
    await waitFor(() => expect(client.responseTime.mock.calls.at(-1)![0].category).toBe("FIRE"));
    expect(client.hotspots.mock.calls.at(-1)![0].category).toBe("FIRE");
    expect(client.categoryBreakdown.mock.calls.at(-1)![0].category).toBeUndefined();
    expect(client.resourceUtilization.mock.calls.at(-1)![0].category).toBeUndefined();
  });

  it("shows an API failure instead of empty panels", async () => {
    const { ApiError } = await import("@raksha/api-client");
    client.responseTime.mockRejectedValue(new ApiError(503, { code: "SERVICE_BUSY", message: "The system is very busy." }));
    render(<AnalyticsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/very busy/i);
    expect(screen.queryByRole("list", { name: "Incidents by category" })).toBeNull();
  });

  it("sends a role that cannot see analytics home, without fetching", async () => {
    currentUser = { id: "u2", role: "RESPONDER" };
    render(<AnalyticsPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(client.responseTime).not.toHaveBeenCalled();
  });
});
