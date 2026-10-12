import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ signIn: vi.fn().mockResolvedValue(undefined) }),
}));

/** Synthetic data only: nothing here belongs to a real person. */
const SYNTHETIC = {
  name: "Synthetic Tester",
  email: "synthetic.tester@example.org",
  password: "correct-horse-battery-staple",
};

async function renderRegisterPage() {
  // The API client is a module-level singleton built from the env at first use.
  vi.resetModules();
  const { default: RegisterPage } = await import("@/app/register/page");
  render(<RegisterPage />);
}

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/full name/i), SYNTHETIC.name);
  await user.type(screen.getByLabelText(/email address/i), SYNTHETIC.email);
  await user.type(screen.getByLabelText(/^password/i), SYNTHETIC.password);
  await user.click(screen.getByRole("button", { name: /create account/i }));
}

describe("the registration page", () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    fetchSpy.mockReset();
    vi.stubGlobal("fetch", fetchSpy);
    vi.stubEnv("NODE_ENV", "production");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("explains the missing backend instead of blaming the visitor's connection", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://raksha-backend-not-deployed.invalid");
    await renderRegisterPage();

    await fillAndSubmit();

    const alert = await screen.findAllByRole("alert");
    const text = alert.map((node) => node.textContent).join(" ");
    expect(text).toContain("NEXT_PUBLIC_API_BASE_URL");
    expect(text).toContain("placeholder");
    expect(text).not.toMatch(/check your connection/i);
    // It never even tried: a request to a name that cannot resolve is what produced
    // the old misleading message.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("registers against the configured backend when there is one", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.acme.io");
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ id: "u1", role: "CITIZEN" }), { status: 201 }),
    );
    await renderRegisterPage();

    await fillAndSubmit();

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.acme.io/api/v1/auth/register");
    expect(init.method).toBe("POST");
    // Only what the form collected goes out: no role field to tamper with.
    expect(Object.keys(JSON.parse(String(init.body))).sort()).toEqual([
      "email",
      "full_name",
      "password",
      "phone",
    ]);
  });

  it("shows the server's own message for a duplicate email", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.acme.io");
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "EMAIL_ALREADY_REGISTERED",
            message: "An account with this email address already exists.",
          },
        }),
        { status: 409 },
      ),
    );
    await renderRegisterPage();

    await fillAndSubmit();

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });

  it("keeps the connection message for a genuine network failure", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.acme.io");
    fetchSpy.mockRejectedValue(new TypeError("Failed to fetch"));
    await renderRegisterPage();

    await fillAndSubmit();

    expect(await screen.findByText(/could not reach the server/i)).toBeInTheDocument();
  });
});
