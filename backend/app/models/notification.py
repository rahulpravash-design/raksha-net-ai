"""Notifications, and the record of what actually reached the recipient.

A delivery row exists per channel, including the channels this deployment has
no provider for. Those are recorded as ``UNAVAILABLE`` rather than omitted:
``docs/ROADMAP.md`` Phase 13 requires that an emergency-critical channel is
never silently dropped, and "we never tried" has to be visible to be true.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DeliveryStatus, NotificationChannel, NotificationKind
from app.models.user import User


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One thing one person needs to know."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, name="notification_kind", native_enum=True),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=True,
    )
    dispatch_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatches.id", ondelete="CASCADE"),
        nullable=True,
    )
    #: Small, non-sensitive extras for the UI (a reference code, a status).
    #: Never coordinates, never contact details.
    context: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship()
    deliveries: Mapped[list[NotificationDelivery]] = relationship(
        back_populates="notification",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read_at"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Notification {self.kind} for {self.user_id}>"


class NotificationDelivery(UUIDPrimaryKeyMixin, Base):
    """What happened when we tried to reach the recipient on one channel."""

    __tablename__ = "notification_deliveries"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", native_enum=True),
        nullable=False,
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status", native_enum=True),
        nullable=False,
        default=DeliveryStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    notification: Mapped[Notification] = relationship(back_populates="deliveries")

    __table_args__ = (Index("ix_deliveries_channel_status", "channel", "status"),)
