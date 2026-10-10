"""Authentication schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserRead

#: A six-digit authenticator code, or a recovery code (letters, with optional dashes
#: or spaces — ``ABCD-EFGH-JKMN``). The two shapes cannot be confused.
SECOND_FACTOR_PATTERN = r"^(\d{6}|[A-Za-z][A-Za-z -]{10,22}[A-Za-z])$"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    #: Required only for an account with MFA enabled: an authenticator code or a
    #: one-time recovery code.
    mfa_code: str | None = Field(default=None, pattern=SECOND_FACTOR_PATTERN)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - a scheme name, not a secret
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    refresh_token: str
    user: UserRead


class MfaEnrollResponse(BaseModel):
    """The shared secret, shown once so it can be added to an authenticator app."""

    secret: str
    provisioning_uri: str = Field(description="An otpauth:// URI for a QR code.")


class MfaCodeRequest(BaseModel):
    """Confirms enrolment: only an authenticator code proves the app is set up."""

    code: str = Field(pattern=r"^\d{6}$")


class MfaEnabledResponse(UserRead):
    """The user (as before), plus the recovery codes — shown this once, never again."""

    recovery_codes: list[str] = Field(
        default_factory=list,
        description="Ten one-time codes. Only their hashes are kept; they cannot be shown again.",
    )


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    #: An authenticator code, or a recovery code if the device is lost.
    code: str = Field(pattern=SECOND_FACTOR_PATTERN)


class MfaRecoveryRegenerateRequest(MfaDisableRequest):
    """Same proof as turning two-factor off: the password and a current code."""


class MfaRecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class MfaRecoveryStatus(BaseModel):
    remaining: int = Field(ge=0, description="Unused recovery codes.")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)
    #: Required only for an account with MFA enabled.
    mfa_code: str | None = Field(default=None, pattern=SECOND_FACTOR_PATTERN)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=1, max_length=128)


class RecoveryStatus(BaseModel):
    #: Whether this deployment can send recovery email at all. Lets the sign-in
    #: screens say "ask an administrator" instead of promising a message that
    #: will never arrive.
    email_available: bool
