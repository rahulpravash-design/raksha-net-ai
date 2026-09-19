"""Notification business rules: compose, record, and attempt delivery.

Phase 13. Notifying somebody must never be able to break the thing that
triggered it: :meth:`notify` catches its own failures, because a status change
that succeeded should not be rolled back because an SMS gateway was down.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.enums import (
    DeliveryStatus,
    NotificationChannel,
    NotificationKind,
)
from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.services.notifiers import get_notifier
from app.utils.time import utcnow

logger = get_logger(__name__)

#: Channels attempted for every notification. IN_APP always succeeds because
#: it is this database; the rest go through a provider that may not exist.
DEFAULT_CHANNELS: tuple[NotificationChannel, ...] = (NotificationChannel.IN_APP,)

#: Kinds important enough to also attempt on an external channel, where one
#: exists. A status change on someone's own report is worth an SMS; a routine
#: system message is not.
URGENT_KINDS: frozenset[NotificationKind] = frozenset(
    {
        NotificationKind.DISPATCH_ASSIGNED,
        NotificationKind.DISPATCH_CANCELLED,
        NotificationKind.INCIDENT_STATUS_CHANGED,
    }
)
URGENT_CHANNELS: tuple[NotificationChannel, ...] = (NotificationChannel.SMS,)


class NotificationService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = NotificationRepository(session)

    # -- sending ------------------------------------------------------------
    def notify(
        self,
        user: User,
        *,
        kind: NotificationKind,
        title: str,
        body: str,
        incident_id: uuid.UUID | None = None,
        dispatch_id: uuid.UUID | None = None,
        context: dict[str, str] | None = None,
        commit: bool = False,
    ) -> Notification | None:
        """Record a notification and attempt every channel it warrants.

        Returns ``None`` if notifying failed outright. The caller is expected
        to carry on: the operational change it is reporting already happened,
        and undoing it because a message failed would be the worse outcome.
        """
        try:
            notification = Notification(
                user_id=user.id,
                kind=kind,
                title=title,
                body=body,
                incident_id=incident_id,
                dispatch_id=dispatch_id,
                context=context,
            )
            self.repo.add(notification)

            channels = list(DEFAULT_CHANNELS)
            if kind in URGENT_KINDS and user.phone:
                channels.extend(URGENT_CHANNELS)

            for channel in channels:
                self._attempt(notification, channel, user)

            if commit:
                self.session.commit()
                self.session.refresh(notification)
            return notification
        except Exception:  # pragma: no cover - defensive, see the docstring
            logger.exception(
                "notification_failed",
                extra={"user_id": str(user.id), "kind": kind.value},
            )
            return None

    def _attempt(
        self, notification: Notification, channel: NotificationChannel, user: User
    ) -> None:
        now = utcnow()

        if channel is NotificationChannel.IN_APP:
            # The inbox is this database; the row above *is* the delivery.
            delivery = NotificationDelivery(
                notification_id=notification.id,
                channel=channel,
                status=DeliveryStatus.DELIVERED,
                attempts=1,
                delivered_at=now,
                created_at=now,
            )
            self.repo.add_delivery(delivery)
            return

        recipient = user.phone if channel is NotificationChannel.SMS else user.email
        outcome = get_notifier(channel, self.settings).send(
            recipient=recipient or "",
            title=notification.title,
            body=notification.body,
        )
        delivery = NotificationDelivery(
            notification_id=notification.id,
            channel=channel,
            status=outcome.status,
            attempts=1,
            detail=outcome.detail,
            delivered_at=now if outcome.status is DeliveryStatus.DELIVERED else None,
            created_at=now,
        )
        self.repo.add_delivery(delivery)

    # -- reading ------------------------------------------------------------
    def list_for_user(
        self, user: User, *, offset: int, limit: int, unread_only: bool = False
    ) -> tuple[list[Notification], int]:
        return self.repo.list_for_user(
            user.id, offset=offset, limit=limit, unread_only=unread_only
        )

    def unread_count(self, user: User) -> int:
        return self.repo.unread_count(user.id)

    def mark_read(self, notification_id: uuid.UUID, *, user: User) -> Notification:
        notification = self.repo.get(notification_id)
        # Someone else's notification reads as absent, not as forbidden.
        if notification is None or notification.user_id != user.id:
            raise NotFoundError("Notification not found.")

        if notification.read_at is None:
            notification.read_at = utcnow()
            self.session.commit()
            self.session.refresh(notification)
        return notification

    def mark_all_read(self, user: User) -> int:
        count = self.repo.mark_all_read(user.id, when=utcnow())
        self.session.commit()
        return count
