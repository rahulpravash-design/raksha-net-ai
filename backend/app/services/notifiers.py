"""The boundary between this platform and an external messaging provider.

Same shape as the AI boundary, for the same reason: the core must work with
the provider entirely absent. :class:`NullNotifier` is not a stub awaiting
completion — it is the configured behaviour of a deployment with no SMS,
email or push contract, and it reports that honestly rather than pretending
a message went out.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol, runtime_checkable

from app.core.config import Settings
from app.core.logging import get_logger
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


logger = get_logger(__name__)


class SmtpNotifier:
    """Sends email through the configured SMTP server.

    It never raises: a mail server that is down must not break the request that
    wanted to send (a recovery request, a security notice). A failure becomes a
    ``FAILED`` outcome whose detail names the kind of error but never carries a
    credential or the message.
    """

    channel = NotificationChannel.EMAIL

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, recipient: str, title: str, body: str) -> DeliveryOutcome:
        if not recipient or "\n" in recipient or "\r" in recipient:
            return DeliveryOutcome(DeliveryStatus.FAILED, "No valid recipient address.")
        message = EmailMessage()
        message["From"] = self.settings.email_from
        message["To"] = recipient
        # Headers cannot hold line breaks; a subject built from user data must
        # not be able to add one.
        message["Subject"] = " ".join(title.split())
        message["Message-ID"] = make_msgid(domain="raksha.invalid")
        message.set_content(body)
        try:
            self._deliver(message)
        except (OSError, smtplib.SMTPException) as error:
            logger.warning("email_send_failed", extra={"error": type(error).__name__})
            return DeliveryOutcome(
                DeliveryStatus.FAILED,
                f"The mail server did not accept it ({type(error).__name__}).",
            )
        return DeliveryOutcome(DeliveryStatus.DELIVERED)

    def _deliver(self, message: EmailMessage) -> None:
        s = self.settings
        host, port, timeout = s.smtp_host or "", s.smtp_port, s.smtp_timeout_seconds
        if s.smtp_security == "ssl":
            connection: smtplib.SMTP = smtplib.SMTP_SSL(
                host, port, timeout=timeout, context=ssl.create_default_context()
            )
        else:
            connection = smtplib.SMTP(host, port, timeout=timeout)
        with connection:
            connection.ehlo()
            if s.smtp_security == "starttls":
                connection.starttls(context=ssl.create_default_context())
                connection.ehlo()
            if s.smtp_username:
                password = s.smtp_password.get_secret_value() if s.smtp_password else ""
                connection.login(s.smtp_username, password)
            connection.send_message(message)


def get_notifier(channel: NotificationChannel, settings: Settings) -> Notifier:
    """Return the configured notifier for ``channel``.

    Email is real when an SMTP host is configured; SMS and push are still null
    notifiers. Wiring another provider (Twilio, FCM) means returning it here and
    nothing else in the platform changes — the service layer already handles an
    outcome it cannot deliver.
    """
    if channel is NotificationChannel.EMAIL and settings.email_configured:
        return SmtpNotifier(settings)
    return NullNotifier(channel)
