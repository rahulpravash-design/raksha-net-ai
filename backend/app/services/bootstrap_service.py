"""Creation of the first super administrator.

Administrators are created by an existing administrator (``AuthService.create_user``),
and self-registration only makes citizens, so a new deployment has no way to get its
first one. This service is that way in, deliberately narrow:

* it runs only when **no administrator account of any kind exists** (active or not), so
  it cannot be used later to mint more of them;
* it creates exactly one role, ``SUPER_ADMIN`` - the only role the API will not hand out
  to an ordinary administrator, and the one that can manage other administrators;
* it is reached from an operator's shell (``app.cli.create_first_admin``), never over
  HTTP, so there is no setup page for anyone to find or race;
* it holds a database lock while it decides, so two simultaneous runs cannot both win;
* the account must replace its password at first sign-in and, where policy requires it,
  enrol two-factor authentication - the same gates as any administrator-created account.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AdminAlreadyExistsError, EmailAlreadyRegisteredError
from app.core.logging import get_logger
from app.core.security import hash_password, validate_password_strength
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import FirstAdminCreate
from app.services.audit_service import AuditAction, AuditService

logger = get_logger(__name__)


class BootstrapService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    def create_first_admin(self, payload: FirstAdminCreate) -> User:
        """Create the first super administrator, or raise and change nothing.

        Raises :class:`WeakPasswordError`, :class:`AdminAlreadyExistsError` or
        :class:`EmailAlreadyRegisteredError`.
        """
        validate_password_strength(payload.password, self.settings)

        # Everything below is decided under one lock, released when the transaction ends
        # (the commit, or the caller closing the session after an error), so the check
        # and the insert are one step.
        self.users.lock_admin_bootstrap()
        if self.users.administrator_count() > 0:
            raise AdminAlreadyExistsError()
        if self.users.email_exists(payload.email):
            raise EmailAlreadyRegisteredError()

        user = User(
            email=payload.email,
            full_name=payload.full_name.strip(),
            phone=payload.phone,
            hashed_password=hash_password(payload.password, self.settings),
            role=UserRole.SUPER_ADMIN,
            is_active=True,
            # The operator chose this password; the person must replace it.
            must_change_password=True,
        )
        self.users.add(user)
        self.audit.record(
            AuditAction.FIRST_ADMIN_CREATED,
            entity_type="user",
            entity_id=user.id,
            metadata={"role": user.role.value, "via": "cli"},
        )
        self.session.commit()
        logger.info(
            "first_admin_created",
            extra={"user_id": str(user.id), "role": user.role.value},
        )
        return user
