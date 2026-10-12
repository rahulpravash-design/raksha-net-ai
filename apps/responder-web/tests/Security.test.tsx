import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SecurityPage from "@/app/account/security/page";
import { AuthProvider } from "@/components/AuthProvider";

const replace = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push }) }));

const client = {
  me: vi.fn(),
  changePassword: vi.fn(),
  mfaEnroll: vi.fn(),
  mfaEnable: vi.fn(),
  mfaDisable: vi.fn(),
};
let hooks: Array<(() => void) | undefined> = [];
vi.mock("@/lib/api", () => ({
  tokenStore: { getAccessToken: () => "token" },
  getApiClient: (...callbacks: Array<(() => void) | undefined>) => {
    if (callbacks.length) hooks = callbacks;
    return client;
  },
}));

const responder = (extra: Record<string, unknown> = {}) => ({
  id: "u1",
  full_name: "Crew One",
  email: "crew@example.com",
  role: "RESPONDER",
  mfa_enabled: false,
  must_change_password: false,
  ...extra,
});

beforeEach(() => {
  replace.mockReset();
  push.mockReset();
  hooks = [];
  for (const fn of Object.values(client)) fn.mockReset();
  client.me.mockResolvedValue(responder());
  client.mfaEnroll.mockResolvedValue({
    secret: "JBSWY3DPEHPK3PXP",
    provisioning_uri: "otpauth://totp/RAKSHA:crew@example.com?secret=JBSWY3DPEHPK3PXP",
  });
  client.mfaEnable.mockResolvedValue({});
});

function renderPage() {
  return render(
    <AuthProvider>
      <SecurityPage />
    </AuthProvider>,
  );
}

describe("responder account security", () => {
  it("offers password change and two-factor setup", async () => {
    renderPage();
    expect(await screen.findByRole("region", { name: "Password" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Two-factor authentication" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set up two-factor" })).toBeInTheDocument();
  });

  it("walks a responder through enrolment: a key to type, then a code to confirm", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Set up two-factor" }));
    expect(await screen.findByLabelText("Setup key")).toHaveTextContent("JBSW Y3DP EHPK 3PXP");
    expect(screen.getByRole("img", { name: /QR code/ })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Code from the app/), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));
    await waitFor(() => expect(client.mfaEnable).toHaveBeenCalledWith("123456"));
  });

  it("explains an administrator-set password and sends the responder on afterwards", async () => {
    client.me.mockResolvedValue(responder({ must_change_password: true }));
    client.changePassword.mockResolvedValue({});
    renderPage();
    expect(await screen.findByRole("note")).toHaveTextContent(/administrator set your password/i);

    await userEvent.type(screen.getByLabelText(/^Current password/), "temp-password-1");
    await userEvent.type(screen.getByLabelText(/^New password/), "my-own-passphrase-2");
    await userEvent.type(screen.getByLabelText(/^Repeat the new password/), "my-own-passphrase-2");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/assignments"));
  });

  it("is where the app sends a responder whose policy requires setup", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Password" });
    const [, mfaRequired, passwordRequired] = hooks;
    mfaRequired?.();
    passwordRequired?.();
    expect(push).toHaveBeenCalledTimes(2);
    expect(push).toHaveBeenNthCalledWith(1, "/account/security");
    expect(push).toHaveBeenNthCalledWith(2, "/account/security");
  });

  it("sends a signed-out visitor to sign in", async () => {
    const { ApiError } = await import("@raksha/api-client");
    client.me.mockRejectedValue(new ApiError(401, { code: "NOT_AUTHENTICATED", message: "no" }));
    renderPage();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
