"""Shared FastAPI dependencies: database session, identity and authorisation."""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Iterable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    ForbiddenError,
    InactiveAccountError,
    InvalidTokenError,
    MfaEnrollmentRequiredError,
    NotAuthenticatedError,
    PasswordChangeRequiredError,
)
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import (
    DISPATCH_ROLES,
    INCIDENT_VIEW_ROLES,
    OPERATIONAL_ROLES,
    UserRole,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import RequestContext

# ``auto_error=False`` so a missing header raises our own error envelope rather
# than Starlette's default shape.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _client_ip(request: Request) -> str | None:
    """Return the client address only when it really is an IP address.

    ``request.client.host`` is not guaranteed to be one: behind a unix socket,
    or under a test client, it can be an arbitrary label. The audit columns are
    ``INET``, so an unparseable value must become NULL rather than fail the
    request it was only being recorded alongside.
    """
    if request.client is None or not request.client.host:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


Context = Annotated[RequestContext, Depends(get_request_context)]


def get_authenticated_user(
    session: DbSession,
    settings: AppSettings,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    """Resolve the caller from the bearer token.

    The user is loaded on every request rather than trusted from the token, so a
    deactivated account loses access immediately instead of at token expiry.
    """
    if credentials is None or not credentials.credentials:
        raise NotAuthenticatedError()

    payload = decode_access_token(credentials.credentials, settings)
    user = UserRepository(session).get(payload.subject)

    if user is None:
        raise InvalidTokenError()
    if not user.is_active:
        raise InactiveAccountError()

    return user


#: Signed in, with no MFA policy applied. Only the endpoints a person needs in
#: order to *satisfy* that policy (``/auth/me`` and MFA enrolment) use this.
AuthenticatedUser = Annotated[User, Depends(get_authenticated_user)]


def get_current_user(user: AuthenticatedUser, settings: AppSettings) -> User:
    """The caller, once the account policies are met: no administrator-set
    password still in force, and two-factor enrolled where policy requires it.
    This is the default for every endpoint, so a policy cannot be forgotten on a
    new one."""
    if user.must_change_password:
        raise PasswordChangeRequiredError()
    if (
        settings.mfa_required_for_operational
        and user.role in OPERATIONAL_ROLES
        and not user.mfa_enabled
    ):
        raise MfaEnrollmentRequiredError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Build a dependency asserting the caller holds one of ``roles``."""
    allowed = frozenset(roles)

    def _dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise ForbiddenError(
                "Your role does not permit this action.",
                details={"required_roles": sorted(role.value for role in allowed)},
            )
        return user

    return _dependency


def require_any_role(roles: Iterable[UserRole]) -> Callable[[User], User]:
    return require_roles(*roles)


#: An operator who may see the whole incident picture.
OperationalUser = Annotated[User, Depends(require_any_role(OPERATIONAL_ROLES))]

#: An operator who may read incident records (not a hospital operator).
IncidentViewer = Annotated[User, Depends(require_any_role(INCIDENT_VIEW_ROLES))]

#: An operator who may change incident state.
DispatchUser = Annotated[User, Depends(require_any_role(DISPATCH_ROLES))]

#: An administrator.
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN))]
