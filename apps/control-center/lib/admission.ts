import { isConsoleRole, type UserRole } from "@raksha/api-client";

export interface AdmissionRefusal {
  code: "NOT_AN_OPERATOR" | "USE_THE_RESPONDER_APP";
  message: string;
}

/**
 * Who the control centre admits. The API already refuses every endpoint a role
 * may not use; this stops the person reaching a console that would only show
 * errors, and tells them where to go instead.
 *
 * A responder authenticates successfully but works from their assignments in the
 * responder application — incident records are the dispatch side's alone.
 */
export function admissionRefusal(role: UserRole): AdmissionRefusal | null {
  if (isConsoleRole(role)) return null;
  if (role === "RESPONDER") {
    return {
      code: "USE_THE_RESPONDER_APP",
      message:
        "Responders work from their assignments in the responder app. The control centre is for dispatch staff and hospital operators.",
    };
  }
  return {
    code: "NOT_AN_OPERATOR",
    message:
      "This console is for emergency operators. Use the citizen app to file or track a report.",
  };
}
