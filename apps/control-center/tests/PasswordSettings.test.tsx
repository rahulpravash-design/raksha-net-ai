import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@raksha/api-client";

import { PasswordSettings } from "@/components/PasswordSettings";

const client = { changePassword: vi.fn() };
const refreshUser = vi.fn();
const replace = vi.fn();
let currentUser: Record<string, unknown> = {};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ user: currentUser, refreshUser }),
}));

async function fill(current: string, next: string, confirm: string) {
  await userEvent.type(screen.getByLabelText(/^Current password/), current);
  await userEvent.type(screen.getByLabelText(/^New password/), next);
  await userEvent.type(screen.getByLabelText(/^Repeat the new password/), confirm);
}

beforeEach(() => {
  client.changePassword.mockReset().mockResolvedValue({});
  refreshUser.mockReset().mockResolvedValue(undefined);
  replace.mockReset();
  currentUser = { id: "u1", role: "DISPATCHER", mfa_enabled: false, must_change_password: false };
});

describe("PasswordSettings", () => {
  it("blocks mismatched or reused passwords without calling the API", async () => {
    render(<PasswordSettings />);
    await fill("old-password-1", "new-password-2", "typo-password-2");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(await screen.findByText(/do not match/i)).toBeInTheDocument();
    expect(client.changePassword).not.toHaveBeenCalled();
  });

  it("changes the password and says what else happened", async () => {
    render(<PasswordSettings />);
    await fill("old-password-1", "new-password-2", "new-password-2");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    await waitFor(() => expect(client.changePassword).toHaveBeenCalledWith("old-password-1", "new-password-2", undefined));
    expect(await screen.findByRole("status")).toHaveTextContent(/other sessions have been signed out/i);
    expect(screen.getByLabelText(/^Current password/)).toHaveValue("");
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows the server's message for a wrong current password or a weak new one", async () => {
    client.changePassword.mockRejectedValue(new ApiError(400, { code: "WEAK_PASSWORD", message: "Password must be at least 12 characters long." }));
    render(<PasswordSettings />);
    await fill("old-password-1", "short-1", "short-1");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 12 characters/i);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("asks for an authenticator code only when two-factor is on", async () => {
    const { unmount } = render(<PasswordSettings />);
    expect(screen.queryByLabelText(/code from your authenticator/i)).toBeNull();
    unmount();

    currentUser = { ...currentUser, mfa_enabled: true };
    render(<PasswordSettings />);
    await fill("old-password-1", "new-password-2", "new-password-2");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(await screen.findByText(/6-digit code/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/code from your authenticator/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    await waitFor(() => expect(client.changePassword).toHaveBeenCalledWith("old-password-1", "new-password-2", "123456"));
  });

  it("explains an administrator-set password and sends the user on once it is replaced", async () => {
    currentUser = { ...currentUser, must_change_password: true };
    render(<PasswordSettings />);
    expect(screen.getByRole("note")).toHaveTextContent(/administrator set your password/i);
    await fill("temp-password-1", "my-own-password-2", "my-own-password-2");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });
});
