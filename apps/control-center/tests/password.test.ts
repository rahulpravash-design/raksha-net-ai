import { describe, expect, it } from "vitest";

import { validatePasswordChange } from "@/lib/password";

const ok = { current: "old-password-1", next: "new-password-2", confirm: "new-password-2", code: "" };

describe("validatePasswordChange", () => {
  it("accepts a consistent form without MFA", () => {
    expect(validatePasswordChange(ok, false)).toEqual({});
  });
  it("requires every field", () => {
    const errors = validatePasswordChange({ current: "", next: "", confirm: "", code: "" }, false);
    expect(Object.keys(errors).sort()).toEqual(["current", "next"]);
  });
  it("catches a mismatched confirmation", () => {
    expect(validatePasswordChange({ ...ok, confirm: "different" }, false).confirm).toMatch(/do not match/i);
  });
  it("catches reusing the current password", () => {
    expect(validatePasswordChange({ ...ok, next: ok.current, confirm: ok.current }, false).next).toMatch(/different/i);
  });
  it("asks for a code only when MFA is on, and only six digits", () => {
    expect(validatePasswordChange(ok, true).code).toBeDefined();
    expect(validatePasswordChange({ ...ok, code: "12345" }, true).code).toBeDefined();
    expect(validatePasswordChange({ ...ok, code: "123456" }, true)).toEqual({});
  });
  it("does not guess the server's password policy", () => {
    expect(validatePasswordChange({ ...ok, next: "short", confirm: "short" }, false)).toEqual({});
  });
});
