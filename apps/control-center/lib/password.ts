export interface PasswordFormValues {
  current: string;
  next: string;
  confirm: string;
  code: string;
}

export type PasswordFormErrors = Partial<Record<keyof PasswordFormValues, string>>;

/**
 * Checks that catch typing mistakes before a round trip. The server's password
 * rules (minimum length, common passwords) are configuration, so the client does
 * not restate them: it shows the server's own message when they are not met.
 */
export function validatePasswordChange(
  values: PasswordFormValues,
  mfaEnabled: boolean,
): PasswordFormErrors {
  const errors: PasswordFormErrors = {};
  if (values.current === "") errors.current = "Enter your current password.";
  if (values.next === "") errors.next = "Choose a new password.";
  else if (values.next === values.current) {
    errors.next = "The new password must be different from the current one.";
  }
  if (values.next !== "" && values.confirm !== values.next) {
    errors.confirm = "The two new passwords do not match.";
  }
  if (mfaEnabled && !/^\d{6}$/.test(values.code)) {
    errors.code = "Enter the 6-digit code from your authenticator app.";
  }
  return errors;
}
