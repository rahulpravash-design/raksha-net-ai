import { describe, expect, it } from "vitest";

import { USER_ROLES } from "@raksha/api-client";

import { admissionRefusal } from "@/lib/admission";

describe("control-centre admission", () => {
  it("admits the dispatch side and hospital operators", () => {
    for (const role of ["DISPATCHER", "ADMIN", "SUPER_ADMIN", "HOSPITAL_OPERATOR"] as const) {
      expect(admissionRefusal(role)).toBeNull();
    }
  });

  it("sends a responder to the responder app rather than showing a console of errors", () => {
    const refusal = admissionRefusal("RESPONDER");
    expect(refusal?.code).toBe("USE_THE_RESPONDER_APP");
    expect(refusal?.message).toMatch(/responder app/i);
  });

  it("sends a citizen to the citizen app", () => {
    const refusal = admissionRefusal("CITIZEN");
    expect(refusal?.code).toBe("NOT_AN_OPERATOR");
    expect(refusal?.message).toMatch(/citizen app/i);
  });

  it("decides for every role", () => {
    for (const role of USER_ROLES) {
      expect(() => admissionRefusal(role)).not.toThrow();
    }
  });
});
