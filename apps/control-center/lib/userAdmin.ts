import type { AdminUser, CreateUserInput, UserRole } from "@raksha/api-client";

export interface UserFormValues {
  email: string;
  full_name: string;
  phone: string;
  role: UserRole;
  password: string;
}

export type UserFormErrors = Partial<Record<keyof UserFormValues, string>>;

export const EMPTY_USER_FORM: UserFormValues = {
  email: "",
  full_name: "",
  phone: "",
  role: "DISPATCHER",
  password: "",
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Typing-mistake checks only. Password strength and uniqueness are the server's
 * to judge (its minimum length is configuration, so the client does not guess
 * it), and its message is shown if it refuses.
 */
export function validateUserForm(values: UserFormValues): {
  errors: UserFormErrors;
  input: CreateUserInput | null;
} {
  const errors: UserFormErrors = {};
  if (!EMAIL.test(values.email.trim())) errors.email = "Enter a valid email address.";
  const name = values.full_name.trim();
  if (name.length < 2) errors.full_name = "Enter a name of at least 2 characters.";
  if (values.phone.trim() && !/^\+?[0-9][0-9\s\-()]{6,30}$/.test(values.phone.trim())) {
    errors.phone = "Phone number format is not recognised.";
  }
  if (values.password.length === 0) errors.password = "Set an initial password.";

  if (Object.keys(errors).length > 0) return { errors, input: null };
  return {
    errors,
    input: {
      email: values.email.trim().toLowerCase(),
      full_name: name,
      phone: values.phone.trim() || null,
      password: values.password,
      role: values.role,
    },
  };
}

// No look-alike characters (0/O, 1/l/I), so a password read aloud or typed from a
// message is not mistyped.
const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";

/** 20 random characters from the browser's CSPRNG (~115 bits). */
export function generatePassword(random: (n: number) => Uint32Array = randomValues): string {
  const limit = Math.floor(0x1_0000_0000 / ALPHABET.length) * ALPHABET.length;
  let out = "";
  while (out.length < 20) {
    for (const value of random(32)) {
      // Reject values that would bias the modulo.
      if (value < limit && out.length < 20) out += ALPHABET[value % ALPHABET.length];
    }
  }
  return out;
}

function randomValues(n: number): Uint32Array {
  return crypto.getRandomValues(new Uint32Array(n));
}

/** Roles the signed-in administrator may assign. Only a super administrator may grant that role. */
export function assignableRoles(actorRole: UserRole, all: readonly UserRole[]): UserRole[] {
  return all.filter((role) => role !== "SUPER_ADMIN" || actorRole === "SUPER_ADMIN");
}

export interface ManagePermissions {
  canEditProfile: boolean;
  canChangeRoleOrActive: boolean;
  canResetMfa: boolean;
  reason: string | null;
}

/**
 * Mirrors the server's rules so the screen does not offer actions that can only
 * fail: nobody changes their own role/active flag or resets their own MFA, and
 * only a super administrator manages one.
 */
export function permissionsFor(actor: { id: string; role: UserRole }, target: AdminUser): ManagePermissions {
  if (target.role === "SUPER_ADMIN" && actor.role !== "SUPER_ADMIN") {
    return {
      canEditProfile: false,
      canChangeRoleOrActive: false,
      canResetMfa: false,
      reason: "Only a super administrator can manage a super administrator.",
    };
  }
  const self = target.id === actor.id;
  return {
    canEditProfile: true,
    canChangeRoleOrActive: !self,
    canResetMfa: !self && target.mfa_enabled,
    reason: self
      ? "You cannot change your own role or active status, or reset your own MFA. Manage MFA from your account."
      : null,
  };
}
