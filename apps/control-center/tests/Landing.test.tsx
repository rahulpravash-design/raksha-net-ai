import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { IncidentSummary, User, UserRole } from "@raksha/api-client";

import { LandingHero } from "@/components/landing/LandingHero";
import { PlatformSection } from "@/components/landing/PlatformSection";
import { PLATFORM_FEATURES } from "@/components/landing/platformFeatures";
import { featureAccess, globeMode, primaryAction } from "@/lib/landing";
import { incidentMarkers } from "@/lib/markers";

let auth: { user: User | null; loading: boolean } = { user: null, loading: false };
vi.mock("@/components/AuthProvider", () => ({ useAuth: () => auth }));

const api = { incidentQueue: vi.fn(), incidentStats: vi.fn() };
vi.mock("@/lib/api", () => ({ getApiClient: () => api }));

let globe: { markers: { id: string }[]; arcs?: unknown[]; selectedId: string | null; label: string } | null = null;
vi.mock("@/components/3d/GlobeStage", () => ({
  GlobeStage: (props: NonNullable<typeof globe> & { onSelect: (id: string | null) => void }) => {
    globe = props;
    return <div data-testid="globe-mock" />;
  },
}));

const person = (role: UserRole, extra: Partial<User> = {}): User =>
  ({ id: "u1", full_name: "Test Person", email: "t@example.com", role, must_change_password: false, ...extra }) as User;

const incident = (id: string, extra: Partial<IncidentSummary> = {}): IncidentSummary =>
  ({
    id,
    reference_code: `RKS-${id.toUpperCase()}`,
    category: "FIRE",
    status: "RECEIVED",
    priority_band: "CRITICAL",
    latitude: "13.0827",
    longitude: "80.2707",
    ...extra,
  }) as IncidentSummary;

beforeEach(() => {
  auth = { user: null, loading: false };
  globe = null;
  api.incidentQueue.mockReset().mockResolvedValue({ items: [incident("aaa"), incident("bbb", { priority_band: "LOW", category: "FLOOD" })] });
  api.incidentStats.mockReset().mockResolvedValue({ total_open: 2 });
});

describe("incidentMarkers", () => {
  it("makes one marker per incident and invents none", () => {
    const markers = incidentMarkers([incident("aaa"), incident("bbb", { priority_band: null })]);
    expect(markers.map((m) => m.id)).toEqual(["aaa", "bbb"]);
    expect(markers[0]).toMatchObject({ lat: 13.0827, lon: 80.2707, band: "CRITICAL", label: "Fire RKS-AAA" });
    expect(markers[1]?.band).toBeNull();
  });

  it("leaves out a record with unusable coordinates rather than drawing it at 0,0", () => {
    const markers = incidentMarkers([incident("aaa", { latitude: "nope" }), incident("bbb")]);
    expect(markers.map((m) => m.id)).toEqual(["bbb"]);
  });
});

describe("globeMode", () => {
  it("draws nothing until the session is known", () => {
    expect(globeMode(null, true)).toBe("checking");
    expect(globeMode(person("DISPATCHER"), true)).toBe("checking");
  });

  it("shows live incidents to the dispatch side only", () => {
    for (const role of ["DISPATCHER", "ADMIN", "SUPER_ADMIN"] as const) {
      expect(globeMode(person(role), false)).toBe("live");
    }
    for (const role of ["CITIZEN", "RESPONDER", "HOSPITAL_OPERATOR"] as const) {
      expect(globeMode(person(role), false)).toBe("demo");
    }
    expect(globeMode(null, false)).toBe("demo");
  });
});

describe("primaryAction", () => {
  it("points each viewer at their own home", () => {
    expect(primaryAction(null)).toEqual({ href: "/dashboard", label: "ENTER COMMAND CENTER" });
    expect(primaryAction(person("DISPATCHER")).href).toBe("/dashboard");
    expect(primaryAction(person("HOSPITAL_OPERATOR"))).toEqual({ href: "/hospitals", label: "OPEN HOSPITALS" });
    expect(primaryAction(person("DISPATCHER", { must_change_password: true })).href).toBe("/account/security");
  });
});

describe("featureAccess", () => {
  const byId = (id: string) => PLATFORM_FEATURES.find((f) => f.id === id)!;

  it("asks a visitor to sign in", () => {
    for (const feature of PLATFORM_FEATURES) expect(featureAccess(feature, null)).toBe("sign-in");
  });

  it("opens the dispatch screens to the dispatch side only", () => {
    expect(featureAccess(byId("dashboard"), "DISPATCHER")).toBe("open");
    expect(featureAccess(byId("resources"), "HOSPITAL_OPERATOR")).toBe("not-for-role");
    expect(featureAccess(byId("dashboard"), "RESPONDER")).toBe("not-for-role");
  });

  it("opens hospitals to hospital operators as well", () => {
    expect(featureAccess(byId("hospitals"), "HOSPITAL_OPERATOR")).toBe("open");
    expect(featureAccess(byId("hospitals"), "RESPONDER")).toBe("not-for-role");
  });
});

/** Every `page.tsx` under `app/`, as the URL path it serves. */
function routes(dir = join(__dirname, "..", "app"), prefix = ""): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      const segment = /^\(.*\)$/.test(entry) ? "" : `/${entry}`;
      return routes(full, prefix + segment);
    }
    return entry === "page.tsx" ? [prefix || "/"] : [];
  });
}

describe("platform features", () => {
  it("link only to screens that exist", () => {
    const existing = new Set(routes());
    for (const feature of PLATFORM_FEATURES) {
      expect(existing, feature.href).toContain(feature.href);
    }
  });

  it("make no claim the platform cannot back", () => {
    const text = PLATFORM_FEATURES.map((f) => f.summary).join(" ").toLowerCase();
    for (const forbidden of ["autonomous", "automatically dispatch", "guarantee", "real-time satellite"]) {
      expect(text).not.toContain(forbidden);
    }
  });
});

describe("PlatformSection", () => {
  it("offers sign-in to a visitor", () => {
    render(<PlatformSection />);
    expect(screen.getAllByRole("link", { name: /Sign in to open/ })).toHaveLength(PLATFORM_FEATURES.length);
  });

  it("does not offer a hospital operator links that would bounce them", () => {
    auth = { user: person("HOSPITAL_OPERATOR"), loading: false };
    render(<PlatformSection />);
    expect(screen.getAllByText("Not available to your role")).toHaveLength(PLATFORM_FEATURES.length - 1);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/hospitals");
  });

  it("opens everything for a dispatcher", () => {
    auth = { user: person("DISPATCHER"), loading: false };
    render(<PlatformSection />);
    expect(screen.queryByText(/Not available/)).toBeNull();
    expect(screen.getAllByRole("link")).toHaveLength(PLATFORM_FEATURES.length);
  });

  it("says the visuals are not themselves a service", () => {
    render(<PlatformSection />);
    expect(screen.getByText(/do not themselves provide emergency services/)).toBeInTheDocument();
  });
});

describe("LandingHero", () => {
  it("shows a visitor labelled demonstration markers and fetches no incident data", async () => {
    render(<LandingHero />);
    expect(screen.getByText(/Demonstration markers — not live incidents/)).toBeInTheDocument();
    expect(screen.getByText(/sign in to see live incidents/i)).toBeInTheDocument();
    expect(globe?.markers.length).toBeGreaterThan(0);
    expect(globe?.markers.every((m) => m.id.startsWith("demo-"))).toBe(true);
    expect(globe?.arcs?.length).toBeGreaterThan(0);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.incidentQueue).not.toHaveBeenCalled();
    expect(api.incidentStats).not.toHaveBeenCalled();
  });

  it("draws nothing while the session is still being read", () => {
    auth = { user: null, loading: true };
    render(<LandingHero />);
    expect(globe?.markers).toEqual([]);
    expect(screen.queryByText(/Demonstration markers/)).toBeNull();
    expect(api.incidentQueue).not.toHaveBeenCalled();
  });

  it("shows a dispatcher the platform's real open incidents, and no demonstration data", async () => {
    auth = { user: person("DISPATCHER"), loading: false };
    render(<LandingHero />);

    await waitFor(() => expect(screen.getByText(/open incidents?/)).toBeInTheDocument());
    expect(screen.getByRole("region", { name: "Live incidents" })).toBeInTheDocument();
    expect(screen.queryByText(/Demonstration markers/)).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("2 open incidents");

    expect(globe?.markers.map((m) => m.id)).toEqual(["aaa", "bbb"]);
    expect(globe?.arcs).toEqual([]);
    expect(globe?.label).toMatch(/2 open incidents from the platform/);
    expect(api.incidentQueue).toHaveBeenCalledWith(expect.objectContaining({ open_only: true, sort: "priority" }));
  });

  it("names the real incident behind a chip, and offers its page — never its report text", async () => {
    auth = { user: person("DISPATCHER"), loading: false };
    render(<LandingHero />);
    const user = userEvent.setup();

    const chip = await screen.findByRole("button", { name: /RKS-AAA · Fire · Critical/ });
    await user.click(chip);

    expect(globe?.selectedId).toBe("aaa");
    const open = screen.getByRole("link", { name: "Open this incident" });
    expect(open).toHaveAttribute("href", "/incidents/aaa");
    const region = screen.getByRole("region", { name: "Live incidents" });
    expect(within(region).getByText(/critical priority, received/)).toBeInTheDocument();
  });

  it("states a true count when more are open than are drawn", async () => {
    api.incidentStats.mockResolvedValue({ total_open: 120 });
    auth = { user: person("ADMIN"), loading: false };
    render(<LandingHero />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("120 open incidents"));
    expect(screen.getByRole("status")).toHaveTextContent("the 2 highest-priority are on the globe");
  });

  it("says so when there are no open incidents", async () => {
    api.incidentQueue.mockResolvedValue({ items: [] });
    api.incidentStats.mockResolvedValue({ total_open: 0 });
    auth = { user: person("DISPATCHER"), loading: false };
    render(<LandingHero />);
    await waitFor(() => expect(screen.getByText("No open incidents right now.")).toBeInTheDocument());
    expect(globe?.markers).toEqual([]);
  });

  it("shows no incident data, and no demonstration data, when the feed cannot be reached", async () => {
    api.incidentQueue.mockRejectedValue(new Error("down"));
    api.incidentStats.mockRejectedValue(new Error("down"));
    auth = { user: person("DISPATCHER"), loading: false };
    render(<LandingHero />);
    await waitFor(() => expect(screen.getByText(/live feed could not be reached/)).toBeInTheDocument());
    expect(globe?.markers).toEqual([]);
    expect(screen.queryByText(/Demonstration markers/)).toBeNull();
  });

  it("keeps a hospital operator on demonstration data and says why", async () => {
    auth = { user: person("HOSPITAL_OPERATOR"), loading: false };
    render(<LandingHero />);
    expect(screen.getByText(/limited to dispatch staff/)).toBeInTheDocument();
    expect(globe?.markers.every((m) => m.id.startsWith("demo-"))).toBe(true);
    expect(screen.getByRole("link", { name: "OPEN HOSPITALS" })).toHaveAttribute("href", "/hospitals");
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.incidentQueue).not.toHaveBeenCalled();
  });

  it("greets a signed-in user by name and role instead of offering sign-in", () => {
    auth = { user: person("DISPATCHER", { full_name: "Karthik Dispatcher" }), loading: false };
    render(<LandingHero />);
    expect(screen.getByText("Karthik Dispatcher")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Operator sign in" })).toBeNull();
  });
});
