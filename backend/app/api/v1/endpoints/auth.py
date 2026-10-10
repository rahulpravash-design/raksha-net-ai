"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, status

from app.api.deps import AppSettings, AuthenticatedUser, Context, DbSession
from app.core.errors import RateLimitedError
from app.core.rate_limit import get_rate_limiter
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaEnabledResponse,
    MfaEnrollResponse,
    MfaRecoveryCodesResponse,
    MfaRecoveryRegenerateRequest,
    MfaRecoveryStatus,
    PasswordChangeRequest,
    RecoveryStatus,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import Message
from app.schemas.user import UserRead, UserRegister
from app.services.auth_service import AuthService, IssuedTokens, RequestContext
from app.services.email_service import deliver

router = APIRouter(prefix="/auth", tags=["authentication"])


def _enforce_auth_rate_limit(context: RequestContext, settings: AppSettings) -> None:
    """Throttle credential endpoints by client address."""
    if not settings.rate_limit_enabled:
        return
    decision = get_rate_limiter().check(
        f"auth:{context.ip_address or 'unknown'}",
        settings.rate_limit_auth_per_minute,
    )
    if not decision.allowed:
        raise RateLimitedError(retry_after=decision.retry_after)


def _to_response(tokens: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
        user=UserRead.model_validate(tokens.user),
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a citizen account",
)
def register(
    payload: UserRegister,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> UserRead:
    """Create a citizen account.

    Self-registration always produces a ``CITIZEN``. Operational accounts are
    created by an administrator.
    """
    _enforce_auth_rate_limit(context, settings)
    user = AuthService(session, settings).register_citizen(payload, context)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="Sign in")
def login(
    payload: LoginRequest,
    background: BackgroundTasks,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> TokenResponse:
    _enforce_auth_rate_limit(context, settings)
    tokens = AuthService(session, settings).login(payload, context)
    if tokens.used_recovery_code:
        # A recovery code is what someone who has taken the device would not have,
        # and what someone who has taken the *account* might: tell the owner.
        background.add_task(deliver, settings, AuthService.recovery_used_notice(tokens))
    return _to_response(tokens)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate tokens")
def refresh(
    payload: RefreshRequest,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> TokenResponse:
    """Exchange a refresh token for a new pair. The presented token is revoked."""
    _enforce_auth_rate_limit(context, settings)
    return _to_response(
        AuthService(session, settings).refresh(payload.refresh_token, context)
    )


@router.post("/logout", response_model=Message, summary="Sign out")
def logout(
    payload: RefreshRequest,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> Message:
    AuthService(session, settings).logout(payload.refresh_token, context)
    return Message(message="Signed out.")


@router.get("/me", response_model=UserRead, summary="Current user")
def me(user: AuthenticatedUser) -> UserRead:
    """Deliberately not behind the MFA policy: a person told to enrol must be
    able to see who they are and that MFA is what is missing."""
    return UserRead.model_validate(user)


@router.post(
    "/password",
    response_model=TokenResponse,
    summary="Change your own password",
)
def change_password(
    payload: PasswordChangeRequest,
    background: BackgroundTasks,
    user: AuthenticatedUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> TokenResponse:
    """Needs the current password (and a current MFA code when MFA is on).

    Deliberately not behind the account-policy dependency: a person whose
    password was set by an administrator must be able to reach this before
    anything else. Ends every other session and returns fresh tokens for this one.
    """
    _enforce_auth_rate_limit(context, settings)
    tokens = AuthService(session, settings).change_password(
        user, payload.current_password, payload.new_password, payload.mfa_code, context
    )
    background.add_task(deliver, settings, AuthService.changed_notice(tokens.user))
    return _to_response(tokens)


@router.get(
    "/recovery-status",
    response_model=RecoveryStatus,
    summary="Whether self-service password recovery is available",
)
def recovery_status(settings: AppSettings) -> RecoveryStatus:
    return RecoveryStatus(email_available=settings.email_configured)


@router.post(
    "/forgot-password",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for a password recovery email",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    background: BackgroundTasks,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> Message:
    """Always answers the same way. Whether an email is sent is not something the
    caller can learn from the response: the message goes out after it, and only
    for an active account that has not used up its hourly allowance."""
    _enforce_auth_rate_limit(context, settings)
    email = AuthService(session, settings).request_password_reset(payload.email, context)
    background.add_task(deliver, settings, email)
    return Message(
        message="If an account exists for that address and email is set up, "
        "a recovery link is on its way."
    )


@router.post(
    "/reset-password",
    response_model=Message,
    summary="Set a new password from a recovery link",
)
def reset_password(
    payload: ResetPasswordRequest,
    background: BackgroundTasks,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> Message:
    """Spends the link, ends every session and clears any lockout. Does not sign
    the person in: they sign in normally, and two-factor still applies."""
    _enforce_auth_rate_limit(context, settings)
    notice = AuthService(session, settings).complete_password_reset(
        payload.token, payload.new_password, context
    )
    background.add_task(deliver, settings, notice)
    return Message(message="Your password has been changed. You can sign in now.")


@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    summary="Begin TOTP MFA enrolment",
)
def mfa_enroll(
    user: AuthenticatedUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> MfaEnrollResponse:
    """Returns a new shared secret. MFA stays off until ``/mfa/enable`` is
    called with a code generated from it."""
    _enforce_auth_rate_limit(context, settings)
    secret, uri = AuthService(session, settings).begin_mfa_enrollment(user, context)
    return MfaEnrollResponse(secret=secret, provisioning_uri=uri)


@router.post(
    "/mfa/enable",
    response_model=MfaEnabledResponse,
    summary="Confirm and enable MFA",
)
def mfa_enable(
    payload: MfaCodeRequest,
    user: AuthenticatedUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> MfaEnabledResponse:
    """Turns two-factor on and returns the user together with ten one-time recovery
    codes. This response is the only time they exist in plain form."""
    _enforce_auth_rate_limit(context, settings)
    enabled, codes = AuthService(session, settings).enable_mfa(
        user, payload.code, context
    )
    return MfaEnabledResponse(
        **UserRead.model_validate(enabled).model_dump(), recovery_codes=codes
    )


@router.get(
    "/mfa/recovery-codes",
    response_model=MfaRecoveryStatus,
    summary="How many recovery codes are left",
)
def mfa_recovery_status(
    user: AuthenticatedUser, session: DbSession, settings: AppSettings
) -> MfaRecoveryStatus:
    """A count, never the codes: they cannot be shown again."""
    return MfaRecoveryStatus(
        remaining=AuthService(session, settings).recovery_codes_remaining(user)
    )


@router.post(
    "/mfa/recovery-codes",
    response_model=MfaRecoveryCodesResponse,
    summary="Replace the recovery codes",
)
def mfa_regenerate_recovery_codes(
    payload: MfaRecoveryRegenerateRequest,
    user: AuthenticatedUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> MfaRecoveryCodesResponse:
    """Needs the password and a current code (authenticator or recovery). Every
    earlier code stops working; the new ones are shown once, here."""
    _enforce_auth_rate_limit(context, settings)
    codes = AuthService(session, settings).regenerate_recovery_codes(
        user, payload.password, payload.code, context
    )
    return MfaRecoveryCodesResponse(recovery_codes=codes)


@router.post("/mfa/disable", response_model=UserRead, summary="Disable MFA")
def mfa_disable(
    payload: MfaDisableRequest,
    user: AuthenticatedUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> UserRead:
    """Needs the password and a current code, not just a session."""
    _enforce_auth_rate_limit(context, settings)
    disabled = AuthService(session, settings).disable_mfa(
        user, payload.password, payload.code, context
    )
    return UserRead.model_validate(disabled)
