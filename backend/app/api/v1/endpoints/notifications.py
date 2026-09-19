"""The in-app notification inbox.

Every endpoint here is scoped to the authenticated caller's own notifications.
There is no "read anyone's inbox" route, for any role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Message, Page
from app.schemas.notification import NotificationRead, UnreadCount
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationRead], summary="Your notifications")
def list_notifications(
    user: CurrentUser,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    unread_only: bool = False,
) -> Page[NotificationRead]:
    rows, total = NotificationService(session).list_for_user(
        user,
        offset=(page - 1) * page_size,
        limit=page_size,
        unread_only=unread_only,
    )
    return Page.build(
        [NotificationRead.model_validate(row) for row in rows], total, page, page_size
    )


@router.get("/unread-count", response_model=UnreadCount, summary="Unread badge count")
def unread_count(user: CurrentUser, session: DbSession) -> UnreadCount:
    return UnreadCount(unread=NotificationService(session).unread_count(user))


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark one as read",
)
def mark_read(
    notification_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> NotificationRead:
    notification = NotificationService(session).mark_read(notification_id, user=user)
    return NotificationRead.model_validate(notification)


@router.post("/read-all", response_model=Message, summary="Mark everything as read")
def mark_all_read(user: CurrentUser, session: DbSession) -> Message:
    count = NotificationService(session).mark_all_read(user)
    return Message(message=f"Marked {count} notifications as read.")
