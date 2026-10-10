"""The words of the emails this platform sends.

Plain text only, and nothing about an incident: email is not a secure channel,
so these carry an account link or a security notice and no operational data.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.models.enums import UserRole


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    recipient: str
    subject: str
    body: str


def app_base_url(settings: Settings, role: UserRole) -> str:
    """The front end this person uses. Fixed by configuration, never by the request."""
    if role is UserRole.CITIZEN:
        base = settings.citizen_app_url
    elif role is UserRole.RESPONDER:
        base = settings.responder_app_url
    else:
        base = settings.control_center_url
    return base.rstrip("/")


def password_reset_email(
    settings: Settings, *, recipient: str, name: str, role: UserRole, token: str
) -> OutgoingEmail:
    link = f"{app_base_url(settings, role)}/reset-password?token={token}"
    minutes = settings.password_reset_token_minutes
    return OutgoingEmail(
        recipient=recipient,
        subject="Reset your RAKSHA NET AI password",
        body=(
            f"Hello {name},\n\n"
            "Someone asked to reset the password for your RAKSHA NET AI account. "
            f"To choose a new one, open this link within {minutes} minutes:\n\n"
            f"{link}\n\n"
            "The link works once. If you did not ask for this, ignore this message: "
            "your password has not changed and nobody can use the link without "
            "access to this inbox.\n"
        ),
    )


def password_changed_email(*, recipient: str, name: str) -> OutgoingEmail:
    return OutgoingEmail(
        recipient=recipient,
        subject="Your RAKSHA NET AI password was changed",
        body=(
            f"Hello {name},\n\n"
            "The password for your RAKSHA NET AI account was just changed, and every "
            "other session was signed out.\n\n"
            "If this was you, there is nothing to do. If it was not, ask an "
            "administrator to reset your password and your second factor straight away.\n"
        ),
    )
