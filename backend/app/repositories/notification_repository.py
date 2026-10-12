"""Notification persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationDelivery


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, notification: Notification) -> Notification:
        self.session.add(notification)
        self.session.flush()
        return notification

    def add_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery:
        self.session.add(delivery)
        self.session.flush()
        return delivery

    def get(self, notification_id: uuid.UUID) -> Notification | None:
        return self.session.get(Notification, notification_id)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))

        total = int(
            self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = (
            self.session.scalars(
                stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
            )
            .unique()
            .all()
        )
        return list(rows), total

    def unread_count(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        return int(self.session.scalar(stmt) or 0)

    def mark_all_read(self, user_id: uuid.UUID, *, when: datetime) -> int:
        # A DML execute returns a CursorResult; only that carries `rowcount`.
        result = cast(
            "CursorResult[Any]",
            self.session.execute(
                update(Notification)
                .where(Notification.user_id == user_id, Notification.read_at.is_(None))
                .values(read_at=when)
            ),
        )
        return int(result.rowcount or 0)
