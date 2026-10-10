import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type User } from "@raksha/api-client";

import { MfaSettings, groupSecret } from "@/components/MfaSettings";
import { QrCode } from "@/components/QrCode";

const client = { mfaEnroll: vi.fn(), mfaEnable: vi.fn(), mfaDisable: vi.fn() };
const refreshUser = vi.fn();
let currentUser: Partial<User> = {};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ user: currentUser, refreshUser }),
}));

const URI = "otpauth://totp/RAKSHA:dana@example.com?secret=JBSWY3DPEHPK3PXP&issuer=RAKSHA";

beforeEach(() => {
  for (const fn of Object.values(client)) fn.mockReset();
  refreshUser.mockReset().mockResolvedValue(undefined);
  currentUser = { id: "u1", mfa_enabled: false };
  client.mfaEnroll.mockResolvedValue({ secret: "JBSWY3DPEHPK3PXP", provisioning_uri: URI });
  client.mfaEnable.mockResolvedValue({});
  client.mfaDisable.mockResolvedValue({});
});

describe("groupSecret", () => {
  it("splits into groups of four", () => {
    expect(groupSecret("JBSWY3DPEHPK3PXP")).toBe("JBSW Y3DP EHPK 3PXP");
    expect(groupSecret("ab cd")).toBe("abcd");
  });
});

describe("QrCode", () => {
  it("draws an accessible, dark-on-white code", () => {
    render(<QrCode value={URI} label="QR for the app" />);
    const svg = screen.getByRole("img", { name: "QR for the app" });
    expect(svg.querySelector("path")?.getAttribute("d")?.length).toBeGreaterThan(200);
    expect(svg).toHaveClass("bg-white");
  });
  it("renders different codes for different data", () => {
    const { container, rerender } = render(<QrCode value="aaaa" label="x" />);
    const first = container.querySelector("path")?.getAttribute("d");
    rerender(<QrCode value="bbbbbbbbbbbbbbbb" label="x" />);
    expect(container.querySelector("path")?.getAttribute("d")).not.toEqual(first);
  });
});

describe("MfaSettings — turning it on", () => {
  it("shows the QR, the key and the no-recovery warning, and sends nothing until a code is confirmed", async () => {
    render(<MfaSettings />);
    expect(screen.getByText("○ Off")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));

    expect(await screen.findByRole("img", { name: /qr code/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Setup key")).toHaveTextContent("JBSW Y3DP EHPK 3PXP");
    expect(screen.getByText(/no backup codes/i)).toBeInTheDocument();
    expect(client.mfaEnable).not.toHaveBeenCalled();
  });

  it("rejects a malformed code locally", async () => {
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "12ab");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/6-digit/i);
    expect(client.mfaEnable).not.toHaveBeenCalled();
  });

  it("confirms with the code, refreshes the user and says what changes", async () => {
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));
    await waitFor(() => expect(client.mfaEnable).toHaveBeenCalledWith("123456"));
    await waitFor(() => expect(refreshUser).toHaveBeenCalled());
    expect(await screen.findByRole("status")).toHaveTextContent(/asked for a code each time you sign in/i);
    expect(screen.queryByLabelText("Setup key")).toBeNull();
  });

  it("shows the server's message for a wrong code and keeps the enrolment open", async () => {
    client.mfaEnable.mockRejectedValue(new ApiError(400, { code: "INVALID_MFA_CODE", message: "That verification code is incorrect or has expired." }));
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.type(await screen.findByLabelText(/code from the app/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /turn on/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect or has expired/i);
    expect(screen.getByLabelText("Setup key")).toBeInTheDocument();
  });

  it("can be cancelled, discarding the key", async () => {
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /set up two-factor/i }));
    await userEvent.click(await screen.findByRole("button", { name: /cancel/i }));
    expect(screen.queryByLabelText("Setup key")).toBeNull();
    expect(screen.getByRole("button", { name: /set up two-factor/i })).toBeInTheDocument();
  });
});

describe("MfaSettings — turning it off", () => {
  beforeEach(() => {
    currentUser = { id: "u1", mfa_enabled: true };
  });

  it("asks for the password and a current code, after an explicit step", async () => {
    render(<MfaSettings />);
    expect(screen.getByText("● On")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /turn off two-factor…/i }));
    expect(client.mfaDisable).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /confirm turn off/i })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Password"), "hunter2-hunter2");
    await userEvent.type(screen.getByLabelText("Current code"), "654321");
    await userEvent.click(screen.getByRole("button", { name: /confirm turn off/i }));
    await waitFor(() => expect(client.mfaDisable).toHaveBeenCalledWith("hunter2-hunter2", "654321"));
    await waitFor(() => expect(refreshUser).toHaveBeenCalled());
  });

  it("shows a refusal and does not claim success", async () => {
    client.mfaDisable.mockRejectedValue(new ApiError(400, { code: "INVALID_MFA_CODE", message: "That verification code is incorrect or has expired." }));
    render(<MfaSettings />);
    await userEvent.click(screen.getByRole("button", { name: /turn off two-factor…/i }));
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.type(screen.getByLabelText("Current code"), "111111");
    await userEvent.click(screen.getByRole("button", { name: /confirm turn off/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect or has expired/i);
    expect(screen.queryByRole("status")).toBeNull();
    expect(refreshUser).not.toHaveBeenCalled();
  });
});
