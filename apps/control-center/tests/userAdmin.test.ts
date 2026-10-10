import { describe, expect, it } from "vitest";

import { USER_ROLES, isLockedNow, type AdminUser } from "@raksha/api-client";

import {
  EMPTY_USER_FORM,
  assignableRoles,
  generatePassword,
  permissionsFor,
  validateUserForm,
} from "@/lib/userAdmin";

const user = (o: Partial<AdminUser> = {}): AdminUser =>
  ({ id: "u2", role: "DISPATCHER", mfa_enabled: true, locked_until: null, failed_login_attempts: 0, ...o }) as AdminUser;

describe("validateUserForm", () => {
  const valid = { ...EMPTY_USER_FORM, email: " New@Example.com ", full_name: "New Person", password: "x" };
  it("normalises a valid form", () => {
    const { errors, input } = validateUserForm({ ...valid, phone: "+91 98765 43210" });
    expect(errors).toEqual({});
    expect(input).toMatchObject({ email: "new@example.com", full_name: "New Person", phone: "+91 98765 43210", role: "DISPATCHER" });
  });
  it("flags each problem", () => {
    const { errors, input } = validateUserForm({ ...EMPTY_USER_FORM, email: "nope", full_name: "A", phone: "abc", password: "" });
    expect(input).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["email", "full_name", "password", "phone"]);
  });
  it("does not guess the server's password policy", () => {
    expect(validateUserForm({ ...valid, password: "short" }).input).not.toBeNull();
  });
});

describe("generatePassword", () => {
  it("is 20 characters with no look-alikes", () => {
    for (let i = 0; i < 50; i++) {
      const p = generatePassword();
      expect(p).toHaveLength(20);
      expect(p).not.toMatch(/[0OIl1]/);
    }
  });
  it("differs between calls", () => {
    expect(generatePassword()).not.toEqual(generatePassword());
  });
  it("rejects biased values instead of folding them", () => {
    // 0xFFFFFFFF is above the unbiased limit and must be skipped, so a source
    // that only ever returns it would loop forever — give it one good value after.
    let calls = 0;
    const source = () => {
      calls += 1;
      const a = new Uint32Array(32);
      a.fill(calls === 1 ? 0xffffffff : 0);
      return a;
    };
    expect(generatePassword(source)).toBe("A".repeat(20));
    expect(calls).toBe(2);
  });
});

describe("assignableRoles", () => {
  it("withholds super administrator from a plain administrator", () => {
    expect(assignableRoles("ADMIN", USER_ROLES)).not.toContain("SUPER_ADMIN");
    expect(assignableRoles("SUPER_ADMIN", USER_ROLES)).toContain("SUPER_ADMIN");
  });
});

describe("permissionsFor", () => {
  it("lets an administrator manage another user", () => {
    expect(permissionsFor({ id: "u1", role: "ADMIN" }, user())).toMatchObject({
      canEditProfile: true,
      canChangeRoleOrActive: true,
      canResetMfa: true,
      canResetPassword: true,
      reason: null,
    });
  });
  it("blocks self-escalation and self MFA reset", () => {
    const p = permissionsFor({ id: "u1", role: "ADMIN" }, user({ id: "u1" }));
    expect(p.canChangeRoleOrActive).toBe(false);
    expect(p.canResetMfa).toBe(false);
    expect(p.canResetPassword).toBe(false);
    expect(p.reason).toMatch(/cannot change your own role/i);
  });
  it("only offers an MFA reset where MFA is on", () => {
    expect(permissionsFor({ id: "u1", role: "ADMIN" }, user({ mfa_enabled: false })).canResetMfa).toBe(false);
  });
  it("leaves a super administrator to another super administrator", () => {
    const target = user({ role: "SUPER_ADMIN" });
    expect(permissionsFor({ id: "u1", role: "ADMIN" }, target).canEditProfile).toBe(false);
    expect(permissionsFor({ id: "u1", role: "SUPER_ADMIN" }, target).canEditProfile).toBe(true);
  });
});

describe("isLockedNow", () => {
  it("is true only inside the window", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(isLockedNow({ locked_until: "2026-01-01T12:10:00Z" }, now)).toBe(true);
    expect(isLockedNow({ locked_until: "2026-01-01T11:50:00Z" }, now)).toBe(false);
    expect(isLockedNow({ locked_until: null }, now)).toBe(false);
  });
});
