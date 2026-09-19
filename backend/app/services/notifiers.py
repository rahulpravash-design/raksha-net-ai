"""The boundary between this platform and an external messaging provider.

Same shape as the AI boundary, for the same reason: the core must work with
the provider entirely absent. :class:`NullNotifier` is not a stub awaiting
completion — it is the configured behaviour of a deployment with no SMS,
email or push contract, and it reports that honestly rather than pretending
a message went out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.config import Settings
from app.models.enums import DeliveryStatus, NotificationChannel


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    status: DeliveryStatus
    detail: str | None = None


@runtime_checkable
class Notifier(Protocol):
    """Sends one message on one channel."""

    channel: NotificationChannel

    def send(self, *, recipient: str, title: str, body: str) -> DeliveryOutcome: ...


class NullNotifier:
    """Declines, and says so.

    The delivery row it produces reads ``UNAVAILABLE``, so an operator asking
    "did the SMS go out?" gets "no provider is configured" rather than silence.
    """

    def __init__(self, channel: NotificationChannel) -> None:
        self.channel = channel

    def send(self, *, recipient: str, title: str, body: str) -> DeliveryOutcome:
        return DeliveryOutcome(
            status=DeliveryStatus.UNAVAILABLE,
            detail=(
                f"No {self.channel.value} provider is configured for this "
                "deployment; the in-app notification was still recorded."
            ),
        )


def get_notifier(channel: NotificationChannel, settings: Settings) -> Notifier:
    """Return the configured notifier for ``channel``.

    Every external channel is a null notifier today. Wiring a real provider
    (Twilio, SES, FCM) means returning it here and nothing else in the
    platform changes — the service layer already handles an outcome it cannot
    deliver.
    """
    return NullNotifier(channel)
