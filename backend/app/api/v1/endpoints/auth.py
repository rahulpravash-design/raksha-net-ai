"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AppSettings, Context, CurrentUser, DbSession
from app.core.errors import RateLimitedError
from app.core.rate_limit import get_rate_limiter
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.common import Message
from app.schemas.user import UserRead, UserRegister
from app.services.auth_service import AuthService, IssuedTokens, RequestContext

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
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> TokenResponse:
    _enforce_auth_rate_limit(context, settings)
    return _to_response(AuthService(session, settings).login(payload, context))


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
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
