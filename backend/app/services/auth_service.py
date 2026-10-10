"""Registration, login, token rotation and logout."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core import totp
from app.core.config import Settings, get_settings
from app.core.errors import (
    AccountLockedError,
    ConflictError,
    EmailAlreadyRegisteredError,
    ForbiddenError,
    InactiveAccountError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    InvalidTokenError,
    MfaRequiredError,
    NotFoundError,
    ValidationError,
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

#: Ceiling on progressive lockout, so a determined attacker cannot lock a
#: legitimate user out for longer than a day.
MAX_LOCKOUT_MINUTES = 24 * 60


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

        # Checked before the password so a locked account cannot be probed:
        # the correct password is refused too until the lock expires.
        self._assert_not_locked(user)

        if not verify_password(payload.password, user.hashed_password):
            self._record_failed_login(payload.email, context, user_id=user.id)
            self._register_failed_attempt(user, context)
            raise InvalidCredentialsError()

        if not user.is_active:
            self._record_failed_login(payload.email, context, user_id=user.id)
            raise InactiveAccountError()

        if user.mfa_enabled:
            self._check_mfa_at_login(user, payload.mfa_code, context)

        user.failed_login_attempts = 0
        user.locked_until = None
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

    def _check_mfa_at_login(
        self, user: User, code: str | None, context: RequestContext
    ) -> None:
        """Second factor, reached only after the password was right.

        A wrong code counts toward lockout exactly as a wrong password does:
        with the password known, a six-digit code is the only thing left to
        guess, and it must not be guessable without limit.
        """
        if code is None:
            raise MfaRequiredError()
        step = totp.verify(user.mfa_secret or "", code, last_step=user.mfa_last_step)
        if step is None:
            self._record_failed_login(user.email, context, user_id=user.id)
            self._register_failed_attempt(user, context)
            raise InvalidMfaCodeError()
        user.mfa_last_step = step

    # -- MFA management -----------------------------------------------------
    def begin_mfa_enrollment(
        self, user: User, context: RequestContext | None = None
    ) -> tuple[str, str]:
        """Issue a fresh pending secret. MFA is not on until a code proves it."""
        context = context or RequestContext()
        if user.mfa_enabled:
            raise ConflictError("MFA is already enabled.", code="MFA_ALREADY_ENABLED")
        secret = totp.new_secret()
        user.mfa_secret = secret
        user.mfa_last_step = None
        self._audit_mfa(AuditAction.MFA_ENROLLMENT_STARTED, user, context)
        self.session.commit()
        uri = totp.provisioning_uri(secret, user.email, self.settings.mfa_issuer)
        return secret, uri

    def enable_mfa(
        self, user: User, code: str, context: RequestContext | None = None
    ) -> User:
        context = context or RequestContext()
        if user.mfa_enabled:
            raise ConflictError("MFA is already enabled.", code="MFA_ALREADY_ENABLED")
        if not user.mfa_secret:
            raise ValidationError(
                "Start MFA enrolment before confirming a code.",
                code="MFA_NOT_ENROLLING",
            )
        step = totp.verify(user.mfa_secret, code)
        if step is None:
            raise InvalidMfaCodeError(status_code=400)
        user.mfa_enabled = True
        user.mfa_last_step = step
        self._audit_mfa(AuditAction.MFA_ENABLED, user, context)
        self.session.commit()
        return user

    def disable_mfa(
        self,
        user: User,
        password: str,
        code: str,
        context: RequestContext | None = None,
    ) -> User:
        """Turning MFA off needs the password *and* a current code, so a stolen
        access token alone cannot strip the second factor."""
        context = context or RequestContext()
        if not user.mfa_enabled:
            raise ConflictError("MFA is not enabled.", code="MFA_NOT_ENABLED")
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError(status_code=400)
        step = totp.verify(user.mfa_secret or "", code, last_step=user.mfa_last_step)
        if step is None:
            raise InvalidMfaCodeError(status_code=400)
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_last_step = None
        self._audit_mfa(AuditAction.MFA_DISABLED, user, context)
        self.session.commit()
        return user

    # -- administrative recovery -------------------------------------------
    def unlock_account(
        self, target: User, *, actor: User, context: RequestContext | None = None
    ) -> User:
        """Clear a lockout. Without this, an attacker who guesses wrong on
        purpose can keep a dispatcher out for up to a day."""
        context = context or RequestContext()
        self._assert_may_manage(target, actor)
        target.failed_login_attempts = 0
        target.locked_until = None
        self._audit_admin(AuditAction.ACCOUNT_UNLOCKED, target, actor, context)
        self.session.commit()
        return target

    def reset_mfa(
        self, target: User, *, actor: User, context: RequestContext | None = None
    ) -> User:
        """Remove a user's second factor (a lost or stolen phone).

        Their sessions are revoked as well: if the device was stolen, the
        sessions it opened are not to be trusted. An administrator cannot do
        this to themselves — that would let a hijacked admin session strip its
        own second factor without the password-and-code that disabling needs.
        """
        context = context or RequestContext()
        if target.id == actor.id:
            raise ForbiddenError("Disable your own MFA from your account settings.")
        self._assert_may_manage(target, actor)
        target.mfa_enabled = False
        target.mfa_secret = None
        target.mfa_last_step = None
        self.tokens.revoke_all_for_user(target.id, utcnow())
        self._audit_admin(AuditAction.MFA_RESET, target, actor, context)
        self.session.commit()
        return target

    @staticmethod
    def _assert_may_manage(target: User, actor: User) -> None:
        if target.role is UserRole.SUPER_ADMIN and actor.role is not UserRole.SUPER_ADMIN:
            raise ForbiddenError("Only a super administrator may manage one.")

    def _audit_admin(
        self, action: str, target: User, actor: User, context: RequestContext
    ) -> None:
        self.audit.record(
            action,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="user",
            entity_id=target.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )

    def _audit_mfa(self, action: str, user: User, context: RequestContext) -> None:
        self.audit.record(
            action,
            actor_id=user.id,
            actor_role=user.role,
            entity_type="user",
            entity_id=user.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )

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

    @staticmethod
    def _assert_not_locked(user: User) -> None:
        if user.locked_until is None:
            return
        remaining = (user.locked_until - utcnow()).total_seconds()
        if remaining > 0:
            raise AccountLockedError(retry_after_seconds=int(remaining) + 1)

    def _register_failed_attempt(self, user: User, context: RequestContext) -> None:
        """Count a wrong password and lock the account once past the threshold.

        The lock doubles for every failure beyond the threshold (progressive
        backoff), capped at a day, and the counter only resets on a
        successful login — so waiting out a lock buys one more guess, not a
        fresh batch.
        """
        user.failed_login_attempts += 1
        threshold = self.settings.account_lockout_threshold
        if user.failed_login_attempts < threshold:
            self.session.commit()
            return

        over = user.failed_login_attempts - threshold
        minutes = min(
            self.settings.account_lockout_minutes * (2 ** min(over, 10)),
            MAX_LOCKOUT_MINUTES,
        )
        user.locked_until = utcnow() + timedelta(minutes=minutes)
        self.audit.record(
            AuditAction.ACCOUNT_LOCKED,
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"locked_minutes": minutes},
        )
        self.session.commit()
        logger.warning("account_locked", extra={"user_id": str(user.id)})
        raise AccountLockedError(retry_after_seconds=minutes * 60)

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
