"""The SMTP notifier, against a real (local, throwaway) SMTP server."""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.enums import DeliveryStatus, NotificationChannel
from app.services.notifiers import NullNotifier, SmtpNotifier, get_notifier

SPEC = importlib.util.spec_from_file_location(
    "dev_mailbox", Path(__file__).resolve().parents[3] / "scripts" / "dev_mailbox.py"
)
dev_mailbox = importlib.util.module_from_spec(SPEC)  # type: ignore[arg-type]
SPEC.loader.exec_module(dev_mailbox)  # type: ignore[union-attr]


@pytest.fixture
def mailbox():
    box = dev_mailbox.Mailbox().start()
    yield box
    box.stop()


def settings_for(port: int, **overrides: object) -> Settings:
    return Settings(
        smtp_host="127.0.0.1",
        smtp_port=port,
        smtp_security="none",
        email_from="RAKSHA <no-reply@raksha.example>",
        **overrides,
    )


def test_a_message_is_delivered_and_arrives_intact(mailbox) -> None:
    notifier = SmtpNotifier(settings_for(mailbox.port))
    outcome = notifier.send(
        recipient="dana@example.com", title="Hello there", body="Line one\nLine two"
    )

    assert outcome.status is DeliveryStatus.DELIVERED
    assert len(mailbox.messages) == 1
    message = mailbox.messages[0]
    assert "dana@example.com" in message["to"]
    assert message["subject"] == "Hello there"
    assert message["body"].strip().replace("\r\n", "\n") == "Line one\nLine two"
    assert "no-reply@raksha.example" in message["raw"]


def test_a_subject_cannot_inject_headers(mailbox) -> None:
    SmtpNotifier(settings_for(mailbox.port)).send(
        recipient="dana@example.com",
        title="Hi\r\nBcc: attacker@example.com",
        body="x",
    )
    raw = mailbox.messages[0]["raw"]
    assert "\r\nBcc:" not in raw
    assert "attacker@example.com" not in mailbox.messages[0]["to"]


@pytest.mark.parametrize("recipient", ["", "a@example.com\r\nBcc: b@example.com"])
def test_an_invalid_recipient_is_refused_without_connecting(recipient: str) -> None:
    outcome = SmtpNotifier(settings_for(1)).send(recipient=recipient, title="t", body="b")
    assert outcome.status is DeliveryStatus.FAILED


def test_an_unreachable_server_is_a_failed_outcome_not_an_exception() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    outcome = SmtpNotifier(settings_for(closed_port, smtp_timeout_seconds=2)).send(
        recipient="dana@example.com", title="t", body="b"
    )
    assert outcome.status is DeliveryStatus.FAILED
    assert "ConnectionRefusedError" in (outcome.detail or "")


def test_the_failure_detail_never_carries_credentials(mailbox) -> None:
    from pydantic import SecretStr

    settings = settings_for(
        1,
        smtp_username="mailer",
        smtp_password=SecretStr("hunter2-secret"),
        smtp_timeout_seconds=1,
    )
    outcome = SmtpNotifier(settings).send(
        recipient="dana@example.com", title="t", body="b"
    )
    assert outcome.status is DeliveryStatus.FAILED
    assert "hunter2-secret" not in (outcome.detail or "")


def test_email_is_real_only_when_a_host_is_configured() -> None:
    off = Settings()
    assert not off.email_configured
    assert isinstance(get_notifier(NotificationChannel.EMAIL, off), NullNotifier)
    on = Settings(smtp_host="mail.example.org")
    assert isinstance(get_notifier(NotificationChannel.EMAIL, on), SmtpNotifier)
    # SMS and push are unaffected.
    assert isinstance(get_notifier(NotificationChannel.SMS, on), NullNotifier)


def test_production_refuses_unencrypted_smtp_and_http_links() -> None:
    from app.core.config import Environment, generate_encryption_key

    base = {
        "environment": Environment.PRODUCTION,
        "debug": False,
        "secret_key": "x" * 40,
        "mfa_required_for_operational": True,
        "encryption_key": generate_encryption_key(),
        "cors_origins": ["https://app.example.org"],
        "smtp_host": "mail.example.org",
    }
    with pytest.raises(RuntimeError) as unsafe:
        Settings(**base, smtp_security="none").assert_safe_for_environment()  # type: ignore[arg-type]
    assert "SMTP_SECURITY" in str(unsafe.value)
    assert "CITIZEN_APP_URL" in str(unsafe.value)

    Settings(
        **base,  # type: ignore[arg-type]
        smtp_security="starttls",
        citizen_app_url="https://citizens.example.org",
        control_center_url="https://control.example.org",
        responder_app_url="https://crews.example.org",
    ).assert_safe_for_environment()
