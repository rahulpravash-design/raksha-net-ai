import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@raksha/api-client";
import { ForgotPasswordForm, ResetPasswordForm, type RecoveryApi } from "@raksha/ui";

import ResetPasswordPage from "@/app/(console)/reset-password/page";

const api = {
  recoveryStatus: vi.fn(),
  requestPasswordReset: vi.fn(),
  resetPassword: vi.fn(),
} satisfies RecoveryApi;
vi.mock("@/lib/api", () => ({ getApiClient: () => api }));

beforeEach(() => {
  api.recoveryStatus.mockReset().mockResolvedValue({ email_available: true });
  api.requestPasswordReset.mockReset().mockResolvedValue(undefined);
  api.resetPassword.mockReset().mockResolvedValue(undefined);
});

describe("ForgotPasswordForm", () => {
  it("says plainly when recovery by email is not set up, and offers no form", async () => {
    api.recoveryStatus.mockResolvedValue({ email_available: false });
    render(<ForgotPasswordForm api={api} signInHref="/login" />);
    expect(await screen.findByText(/not set up for this system/i)).toBeInTheDocument();
    expect(screen.getByText(/ask an administrator/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/email address/i)).toBeNull();
  });

  it("rejects an obviously malformed address without a request", async () => {
    render(<ForgotPasswordForm api={api} signInHref="/login" />);
    await userEvent.type(await screen.findByLabelText(/email address/i), "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: /send the link/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/email address of your account/i);
    expect(api.requestPasswordReset).not.toHaveBeenCalled();
  });

  it("gives the same non-committal answer after submitting", async () => {
    render(<ForgotPasswordForm api={api} signInHref="/login" />);
    await userEvent.type(await screen.findByLabelText(/email address/i), "anyone@example.com");
    await userEvent.click(screen.getByRole("button", { name: /send the link/i }));
    await waitFor(() => expect(api.requestPasswordReset).toHaveBeenCalledWith("anyone@example.com"));
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/if an account exists/i);
    expect(status).toHaveTextContent(/nothing here confirms/i);
  });

  it("shows a network failure instead of pretending it was sent", async () => {
    api.requestPasswordReset.mockRejectedValue(new ApiError(429, { code: "RATE_LIMITED", message: "Too many requests. Please slow down." }));
    render(<ForgotPasswordForm api={api} signInHref="/login" />);
    await userEvent.type(await screen.findByLabelText(/email address/i), "anyone@example.com");
    await userEvent.click(screen.getByRole("button", { name: /send the link/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/too many requests/i);
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("ResetPasswordForm", () => {
  const form = (token: string | null = "tok-1234567890abcdef") => (
    <ResetPasswordForm api={api} token={token} signInHref="/login" forgotHref="/forgot-password" />
  );

  it("needs a token, and says where to get one", () => {
    render(form(null));
    expect(screen.getByText(/needs the link from your recovery email/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute("href", "/forgot-password");
  });

  it("blocks mismatched passwords locally", async () => {
    render(form());
    await userEvent.type(screen.getByLabelText(/^New password/), "one-long-passphrase-1");
    await userEvent.type(screen.getByLabelText(/^Repeat the new password/), "different-passphrase-2");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/do not match/i);
    expect(api.resetPassword).not.toHaveBeenCalled();
  });

  it("changes the password and points to sign-in, without signing in", async () => {
    render(form());
    await userEvent.type(screen.getByLabelText(/^New password/), "one-long-passphrase-1");
    await userEvent.type(screen.getByLabelText(/^Repeat the new password/), "one-long-passphrase-1");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    await waitFor(() => expect(api.resetPassword).toHaveBeenCalledWith("tok-1234567890abcdef", "one-long-passphrase-1"));
    expect(await screen.findByRole("status")).toHaveTextContent(/other session was signed out|every other session/i);
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("keeps the form (and the link) usable after a weak-password refusal", async () => {
    api.resetPassword.mockRejectedValue(new ApiError(400, { code: "WEAK_PASSWORD", message: "Password must be at least 12 characters long." }));
    render(form());
    await userEvent.type(screen.getByLabelText(/^New password/), "short");
    await userEvent.type(screen.getByLabelText(/^Repeat the new password/), "short");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 12 characters/i);
    expect(screen.getByLabelText(/^New password/)).toBeInTheDocument();
  });

  it("switches to a 'link not valid' state when the server says the link is dead", async () => {
    api.resetPassword.mockRejectedValue(new ApiError(400, { code: "INVALID_RESET_TOKEN", message: "This recovery link is invalid or has expired. Request a new one." }));
    render(form());
    await userEvent.type(screen.getByLabelText(/^New password/), "one-long-passphrase-1");
    await userEvent.type(screen.getByLabelText(/^Repeat the new password/), "one-long-passphrase-1");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(await screen.findByText(/link not valid/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new link/i })).toBeInTheDocument();
  });
});

describe("reset page", () => {
  it("reads the token from the link and removes it from the address bar", async () => {
    window.history.replaceState(null, "", "/reset-password?token=abcdefghijklmnopqrstuvwxyz");
    render(<ResetPasswordPage />);
    await userEvent.type(await screen.findByLabelText(/^New password/), "one-long-passphrase-1");
    await userEvent.type(screen.getByLabelText(/^Repeat the new password/), "one-long-passphrase-1");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    await waitFor(() => expect(api.resetPassword).toHaveBeenCalledWith("abcdefghijklmnopqrstuvwxyz", "one-long-passphrase-1"));
    expect(window.location.search).toBe("");
  });
});
