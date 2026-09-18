"""Registration, login, token rotation and logout."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidTokenError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.core.security import (
    burn_password_cycle,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import RefreshToken, User
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import LoginRequest
from app.schemas.user import UserCreate, UserRegister
from app.services.audit_service import AuditAction, AuditService
from app.utils.time import utcnow

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Where a request came from, for audit and session forensics."""

    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    user: User


class AuthService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.audit = AuditService(session)

    # -- registration -------------------------------------------------------
    def register_citizen(
        self, payload: UserRegister, context: RequestContext | None = None
    ) -> User:
        """Self-registration. Always creates a ``CITIZEN``.

        A ``role`` in the request body is not honoured — operational accounts
        are created by an administrator.
        """
        context = context or RequestContext()
        validate_password_strength(payload.password, self.settings)

        if self.users.email_exists(payload.email):
            raise EmailAlreadyRegisteredError()

        user = User(
            email=payload.email,
            full_name=payload.full_name.strip(),
            phone=payload.phone,
            hashed_password=hash_password(payload.password, self.settings),
            role=UserRole.CITIZEN,
            is_active=True,
        )
        self.users.add(user)
        self.audit.record(
            AuditAction.USER_REGISTERED,
            actor_id=user.id,
            actor_role=user.role,
            entity_type="user",
            entity_id=user.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
        self.session.commit()
        logger.info("user_registered", extra={"user_id": str(user.id)})
        return user

    def create_user(
        self,
        payload: UserCreate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> User:
        """Administrative user creation with an explicit role."""
        context = context or RequestContext()
        validate_password_strength(payload.password, self.settings)

        if (
            payload.role is UserRole.SUPER_ADMIN
            and actor.role is not UserRole.SUPER_ADMIN
        ):
            from app.core.errors import ForbiddenError

            raise ForbiddenError("Only a super administrator may create one.")

        if self.users.email_exists(payload.email):
            raise EmailAlreadyRegisteredError()

        user = User(
            email=payload.email,
            full_name=payload.full_name.strip(),
            phone=payload.phone,
            hashed_password=hash_password(payload.password, self.settings),
            role=payload.role,
            is_active=payload.is_active,
        )
        self.users.add(user)
        self.audit.record(
            AuditAction.USER_CREATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="user",
            entity_id=user.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"role": user.role.value},
        )
        self.session.commit()
        return user

    # -- login --------------------------------------------------------------
    def login(
        self, payload: LoginRequest, context: RequestContext | None = None
    ) -> IssuedTokens:
        """Authenticate and issue a token pair.

        An unknown email and a wrong password produce the same error after
        comparable work, so this endpoint is not a user-enumeration oracle.
        """
        context = context or RequestContext()
        user = self.users.get_by_email(payload.email)

        if user is None:
            burn_password_cycle()
            self._record_failed_login(payload.email, context)
            raise InvalidCredentialsError()

        if not verify_password(payload.password, user.hashed_password):
            self._record_failed_login(payload.email, context, user_id=user.id)
            raise InvalidCredentialsError()

        if not user.is_active:
            self._record_failed_login(payload.email, context, user_id=user.id)
            raise InactiveAccountError()

        user.last_login_at = utcnow()
        tokens = self._issue_tokens(user, context)
        self.audit.record(
            AuditAction.LOGIN_SUCCESS,
            actor_id=user.id,
            actor_role=user.role,
            entity_type="user",
            entity_id=user.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
        self.session.commit()
        return tokens

    # -- rotation -----------------------------------------------------------
    def refresh(
        self, raw_token: str, context: RequestContext | None = None
    ) -> IssuedTokens:
        """Rotate a refresh token.

        Presenting an already-revoked token revokes its entire chain: that is
        the signature of a stolen credential being replayed, and the safe
        response is to end every session descended from it.
        """
        context = context or RequestContext()
        stored = self.tokens.get_by_hash(hash_refresh_token(raw_token))
        now = utcnow()

        if stored is None:
            raise InvalidTokenError()

        if stored.revoked_at is not None:
            revoked = self.tokens.revoke_chain(stored, now)
            self.tokens.revoke_all_for_user(stored.user_id, now)
            self.audit.record(
                AuditAction.TOKEN_REUSE_DETECTED,
                actor_id=stored.user_id,
                entity_type="refresh_token",
                entity_id=stored.id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                metadata={"revoked_count": revoked},
            )
            self.session.commit()
            logger.warning(
                "refresh_token_reuse_detected", extra={"user_id": str(stored.user_id)}
            )
            raise InvalidTokenError(
                "This session has been ended for security reasons. Please sign in again."
            )

        if stored.expires_at <= now:
            raise InvalidTokenError("The session has expired. Please sign in again.")

        user = self.users.get(stored.user_id)
        if user is None:
            raise InvalidTokenError()
        if not user.is_active:
            raise InactiveAccountError()

        issued = self._issue_tokens(user, context)
        stored.revoked_at = now
        stored.replaced_by_id = self._last_issued_id

        self.audit.record(
            AuditAction.TOKEN_REFRESHED,
            actor_id=user.id,
            actor_role=user.role,
            entity_type="refresh_token",
            entity_id=stored.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
        self.session.commit()
        return issued

    def logout(self, raw_token: str, context: RequestContext | None = None) -> None:
        """Revoke a refresh token. Idempotent by design — a client signing out
        twice is not an error worth surfacing."""
        context = context or RequestContext()
        stored = self.tokens.get_by_hash(hash_refresh_token(raw_token))
        if stored is None:
            return

        if stored.revoked_at is None:
            stored.revoked_at = utcnow()

        self.audit.record(
            AuditAction.LOGOUT,
            actor_id=stored.user_id,
            entity_type="refresh_token",
            entity_id=stored.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
        self.session.commit()

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    # -- internals ----------------------------------------------------------
    def _issue_tokens(self, user: User, context: RequestContext) -> IssuedTokens:
        access_token, expires_in = create_access_token(
            user.id, user.role.value, settings=self.settings
        )
        raw_refresh, token_hash = generate_refresh_token()
        record = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=utcnow() + timedelta(days=self.settings.refresh_token_expire_days),
            user_agent=context.user_agent,
            ip_address=context.ip_address,
        )
        self.tokens.add(record)
        self._last_issued_id = record.id
        return IssuedTokens(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=raw_refresh,
            user=user,
        )

    def _record_failed_login(
        self,
        email: str,
        context: RequestContext,
        user_id: uuid.UUID | None = None,
    ) -> None:
        self.audit.record(
            AuditAction.LOGIN_FAILED,
            actor_id=user_id,
            entity_type="user",
            entity_id=user_id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            # The email is recorded for abuse investigation; the password never is.
            metadata={"email": email},
        )
        self.session.commit()
