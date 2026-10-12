"""Notification schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    DeliveryStatus,
    NotificationChannel,
    NotificationKind,
)
from app.schemas.common import ORMModel


class DeliveryRead(ORMModel):
    """What happened on one channel.

    ``UNAVAILABLE`` is shown, not hidden: a recipient who expected an SMS
    should be able to see that none was configured to go out.
    """

    channel: NotificationChannel
    status: DeliveryStatus
    attempts: int
    detail: str | None
    delivered_at: datetime | None


class NotificationRead(ORMModel):
    id: uuid.UUID
    kind: NotificationKind
    title: str
    body: str
    incident_id: uuid.UUID | None
    dispatch_id: uuid.UUID | None
    context: dict[str, str] | None
    read_at: datetime | None
    created_at: datetime
    deliveries: list[DeliveryRead] = Field(default_factory=list)


class UnreadCount(BaseModel):
    unread: int
