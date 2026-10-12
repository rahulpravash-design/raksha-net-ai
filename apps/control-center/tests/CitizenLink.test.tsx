import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LandingHero } from "@/components/landing/LandingHero";

vi.mock("@/components/AuthProvider", () => ({ useAuth: () => ({ user: null, loading: false }) }));
vi.mock("@/lib/api", () => ({
  getApiClient: () => ({ incidentQueue: vi.fn(), incidentStats: vi.fn() }),
}));
vi.mock("@/components/3d/GlobeStage", () => ({ GlobeStage: () => <div data-testid="globe-mock" /> }));

let citizenUrl: string | undefined;
vi.mock("@/lib/config", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/config")>()),
  get CITIZEN_APP_URL() {
    return citizenUrl;
  },
}));

describe("the landing page's emergency-reporting link", () => {
  it("points at the configured citizen app", () => {
    citizenUrl = "https://raksha-citizen.netlify.app";
    render(<LandingHero />);
    expect(screen.getByRole("link", { name: /report an emergency/i })).toHaveAttribute(
      "href",
      "https://raksha-citizen.netlify.app/report",
    );
  });

  it("is withheld, with the reason, when no citizen app is configured — never a localhost link", () => {
    citizenUrl = undefined;
    render(<LandingHero />);
    expect(screen.queryByRole("link", { name: /report an emergency/i })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("NEXT_PUBLIC_CITIZEN_APP_URL");
  });
});
