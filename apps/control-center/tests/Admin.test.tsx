import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type AdminUser } from "@raksha/api-client";

import { UserCreateForm } from "@/components/admin/UserCreateForm";
import { UserDetail } from "@/components/admin/UserDetail";
import { HospitalRegisterForm } from "@/components/hospitals/HospitalRegisterForm";

const client = {
  createUser: vi.fn(),
  updateUser: vi.fn(),
  unlockUser: vi.fn(),
  resetUserMfa: vi.fn(),
  adminUsers: vi.fn(),
  createHospital: vi.fn(),
};
vi.mock("@/lib/api", () => ({ getApiClient: () => client }));

function account(o: Partial<AdminUser> = {}): AdminUser {
  return {
    id: "u2", email: "dana@example.com", full_name: "Dana Dispatcher", phone: null, role: "DISPATCHER",
    is_active: true, is_verified: true, mfa_enabled: true, created_at: "", last_login_at: null,
    locked_until: null, failed_login_attempts: 0, ...o,
  };
}
const admin = { id: "u1", role: "ADMIN" as const };

beforeEach(() => {
  for (const fn of Object.values(client)) fn.mockReset();
  client.updateUser.mockResolvedValue(account());
  client.unlockUser.mockResolvedValue(account());
  client.resetUserMfa.mockResolvedValue(account({ mfa_enabled: false }));
  client.adminUsers.mockResolvedValue({ items: [account({ id: "op-1", full_name: "Hana Hospital", role: "HOSPITAL_OPERATOR" })], total: 1 });
});

describe("UserDetail", () => {
  it("shows lockout and offers unlock only while locked", async () => {
    const locked = account({ locked_until: new Date(Date.now() + 600_000).toISOString(), failed_login_attempts: 5 });
    const onChanged = vi.fn();
    const { unmount } = render(<UserDetail user={locked} actor={admin} onChanged={onChanged} />);
    expect(screen.getByText(/locked until/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /unlock account/i }));
    await waitFor(() => expect(client.unlockUser).toHaveBeenCalledWith("u2"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    unmount();

    render(<UserDetail user={account()} actor={admin} onChanged={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /unlock account/i })).toBeNull();
  });

  it("resets two-factor only after a confirmation", async () => {
    render(<UserDetail user={account()} actor={admin} onChanged={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /reset two-factor…/i }));
    expect(client.resetUserMfa).not.toHaveBeenCalled();
    expect(screen.getByText(/end all their sessions/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /confirm mfa reset/i }));
    await waitFor(() => expect(client.resetUserMfa).toHaveBeenCalledWith("u2"));
  });

  it("offers no MFA reset where MFA is off", () => {
    render(<UserDetail user={account({ mfa_enabled: false })} actor={admin} onChanged={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /reset two-factor/i })).toBeNull();
  });

  it("gives an administrator no way to change their own role, deactivate or reset MFA", () => {
    render(<UserDetail user={account({ id: "u1" })} actor={admin} onChanged={vi.fn()} />);
    expect(screen.queryByLabelText("Change role")).toBeNull();
    expect(screen.queryByRole("button", { name: /deactivate/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reset two-factor/i })).toBeNull();
    expect(screen.getByText(/cannot change your own role/i)).toBeInTheDocument();
  });

  it("is read-only for a super administrator when the viewer is a plain administrator", () => {
    render(<UserDetail user={account({ role: "SUPER_ADMIN" })} actor={admin} onChanged={vi.fn()} />);
    expect(screen.getByText(/only a super administrator/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save profile|deactivate|reset/i })).toBeNull();
  });

  it("changes a role only after confirming, and never offers super administrator to an administrator", async () => {
    render(<UserDetail user={account()} actor={admin} onChanged={vi.fn()} />);
    const select = screen.getByLabelText("Change role");
    expect(within(select).queryByText("Super administrator")).toBeNull();
    await userEvent.selectOptions(select, "ADMIN");
    await userEvent.click(screen.getByRole("button", { name: /change role…/i }));
    expect(client.updateUser).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /confirm role change/i }));
    await waitFor(() => expect(client.updateUser).toHaveBeenCalledWith("u2", { role: "ADMIN" }));
  });

  it("deactivates in two steps and shows the server's refusal", async () => {
    client.updateUser.mockRejectedValue(new ApiError(403, { code: "FORBIDDEN", message: "You cannot change your own role or active status." }));
    render(<UserDetail user={account()} actor={admin} onChanged={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /deactivate…/i }));
    expect(client.updateUser).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /confirm deactivate/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot change your own/i);
  });

  it("sends only the changed profile fields", async () => {
    render(<UserDetail user={account()} actor={admin} onChanged={vi.fn()} />);
    const name = screen.getByLabelText(/full name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Dana D.");
    await userEvent.click(screen.getByRole("button", { name: /save profile/i }));
    await waitFor(() => expect(client.updateUser).toHaveBeenCalledWith("u2", { full_name: "Dana D." }));
  });
});

describe("UserCreateForm", () => {
  it("blocks an invalid form without calling the API", async () => {
    render(<UserCreateForm actorRole="ADMIN" onCreated={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(client.createUser).not.toHaveBeenCalled();
  });

  it("creates the account and shows the initial password once", async () => {
    client.createUser.mockResolvedValue(account({ full_name: "New Operator" }));
    const onCreated = vi.fn();
    render(<UserCreateForm actorRole="ADMIN" onCreated={onCreated} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/^email/i), "new@example.com");
    await userEvent.type(screen.getByLabelText(/^full name/i), "New Operator");
    await userEvent.click(screen.getByRole("button", { name: /generate/i }));
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByLabelText("Initial password")).toHaveTextContent(/^\S{20}$/);
    expect(client.createUser).toHaveBeenCalledWith(expect.objectContaining({ email: "new@example.com", role: "DISPATCHER" }));
    expect(screen.getByText(/cannot change it themselves yet/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(onCreated).toHaveBeenCalled();
  });

  it("surfaces a weak-password or duplicate refusal from the server", async () => {
    client.createUser.mockRejectedValue(new ApiError(400, { code: "WEAK_PASSWORD", message: "Password must be at least 12 characters long." }));
    render(<UserCreateForm actorRole="ADMIN" onCreated={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/^email/i), "new@example.com");
    await userEvent.type(screen.getByLabelText(/^full name/i), "New Operator");
    await userEvent.type(screen.getByLabelText(/^initial password/i), "short");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 12 characters/i);
  });

  it("does not offer super administrator to an administrator", () => {
    render(<UserCreateForm actorRole="ADMIN" onCreated={vi.fn()} onCancel={vi.fn()} />);
    expect(within(screen.getByLabelText("Role")).queryByText("Super administrator")).toBeNull();
  });
});

describe("HospitalRegisterForm", () => {
  it("lists hospital operators and links the chosen one", async () => {
    client.createHospital.mockResolvedValue({ id: "h1" });
    const onCreated = vi.fn();
    render(<HospitalRegisterForm onCreated={onCreated} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/^code/i), "GH-9");
    await userEvent.type(screen.getByLabelText(/^name/i), "General");
    await userEvent.type(screen.getByLabelText(/^latitude/i), "13.1");
    await userEvent.type(screen.getByLabelText(/^longitude/i), "80.2");
    await userEvent.selectOptions(await screen.findByLabelText("Hospital operator").then(async (el) => { await screen.findByText(/Hana Hospital/); return el; }), "op-1");
    await userEvent.click(screen.getByRole("button", { name: /register hospital/i }));
    await waitFor(() => expect(client.createHospital).toHaveBeenCalledWith(expect.objectContaining({ code: "GH-9", managed_by_id: "op-1" })));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });

  it("shows the server's message for a duplicate code", async () => {
    client.createHospital.mockRejectedValue(new ApiError(409, { code: "CONFLICT", message: "A hospital with that code already exists." }));
    render(<HospitalRegisterForm onCreated={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/^code/i), "GH-9");
    await userEvent.type(screen.getByLabelText(/^name/i), "General");
    await userEvent.type(screen.getByLabelText(/^latitude/i), "13.1");
    await userEvent.type(screen.getByLabelText(/^longitude/i), "80.2");
    await userEvent.click(screen.getByRole("button", { name: /register hospital/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/already exists/i);
  });
});
