"""User and refresh-token entities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import EncryptedString
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.incident import Incident


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        default=UserRole.CITIZEN,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: Consecutive failed logins since the last success. Reset to 0 on any
    #: successful login (``CLAUDE.md`` section 5, Phase 16 account lockout).
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Set once ``failed_login_attempts`` reaches the configured threshold.
    #: A login attempt against a still-locked account is refused without
    #: even checking the password.
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: TOTP shared secret, encrypted at rest. Present while enrolment is
    #: pending *and* once enabled; ``mfa_enabled`` is what says which.
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The 30-second time step of the last accepted code. A code at or before
    #: it is a replay and is refused, even though it is still inside the window.
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    reported_incidents: Mapped[list[Incident]] = relationship(
        back_populates="reported_by", foreign_keys="Incident.reported_by_id"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} role={self.role}>"


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """An opaque, rotating session credential.

    Only the SHA-256 of the token is stored. ``replaced_by_id`` forms a rotation
    chain; presenting a revoked token revokes the whole chain, which is how
    token theft is detected (``docs/SECURITY.md`` section 2).
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
