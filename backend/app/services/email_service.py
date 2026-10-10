"""Sending the platform's own emails (account recovery and security notices).

Kept apart from :mod:`app.services.notification_service`: that service turns
*incident* events into notifications and deliberately never emails them. This one
sends account mail only, and is called after the response has gone, so a slow
mail server cannot delay a request — or let a caller tell a real account from an
unknown one by how long the answer took.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import DeliveryStatus, NotificationChannel
from app.services.email_messages import OutgoingEmail
from app.services.notifiers import get_notifier

logger = get_logger(__name__)


def deliver(settings: Settings, email: OutgoingEmail | None) -> DeliveryStatus | None:
    """Send ``email`` if there is one and the channel exists. Never raises."""
    if email is None or not settings.email_configured:
        return None
    outcome = get_notifier(NotificationChannel.EMAIL, settings).send(
        recipient=email.recipient, title=email.subject, body=email.body
    )
    if outcome.status is not DeliveryStatus.DELIVERED:
        logger.warning("account_email_not_delivered", extra={"detail": outcome.detail})
    return outcome.status
