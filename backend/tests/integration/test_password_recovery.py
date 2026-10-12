"""Self-service password recovery by email."""

from __future__ import annotations

import re
from datetime import timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_refresh_token
from app.models.enums import DeliveryStatus, UserRole
from app.models.incident import AuditLog
from app.models.user import PasswordResetToken, User
from app.services.notifiers import DeliveryOutcome
from app.utils.time import utcnow

NEW = "recovered-passphrase-2026"
SETTINGS = get_settings()


class Outbox:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, recipient: str, title: str, body: str) -> DeliveryOutcome:
        self.sent.append({"to": recipient, "subject": title, "body": body})
        return DeliveryOutcome(DeliveryStatus.DELIVERED)

    def token(self, index: int = -1) -> str:
        match = re.search(r"token=([\w-]+)", self.sent[index]["body"])
        assert match, self.sent[index]["body"]
        return match.group(1)


@pytest.fixture
def outbox(monkeypatch) -> Outbox:
    """Email switched on, with sending captured instead of going anywhere."""
    box = Outbox()
    monkeypatch.setattr(SETTINGS, "smtp_host", "mail.test")
    monkeypatch.setattr(
        "app.services.email_service.get_notifier", lambda channel, settings: box
    )
    return box


def forgot(client: TestClient, email: str, **headers: str):
    return client.post(
        "/api/v1/auth/forgot-password", json={"email": email}, headers=headers
    )


def reset(client: TestClient, token: str, password: str = NEW):
    return client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": password}
    )


def login(client: TestClient, email: str, password: str, **extra: object):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password, **extra}
    )


# --- availability -----------------------------------------------------------------
def test_recovery_status_says_whether_email_exists(
    client: TestClient, monkeypatch
) -> None:
    assert client.get("/api/v1/auth/recovery-status").json() == {"email_available": False}
    monkeypatch.setattr(SETTINGS, "smtp_host", "mail.test")
    assert client.get("/api/v1/auth/recovery-status").json() == {"email_available": True}


def test_without_a_mail_channel_the_request_is_accepted_and_nothing_is_sent(
    client: TestClient, make_user, monkeypatch
) -> None:
    user = make_user(UserRole.DISPATCHER)
    sent: list[object] = []
    monkeypatch.setattr(
        "app.services.email_service.get_notifier", lambda c, s: sent.append(1) or None
    )
    assert forgot(client, user.email).status_code == 202
    assert sent == []


# --- the request: no enumeration, the right link -----------------------------------
def test_known_and_unknown_addresses_get_the_same_answer(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    known = forgot(client, user.email)
    unknown = forgot(client, "nobody@example.org")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(outbox.sent) == 1 and outbox.sent[0]["to"] == user.email


@pytest.mark.parametrize(
    ("role", "base_attr"),
    [
        (UserRole.CITIZEN, "citizen_app_url"),
        (UserRole.RESPONDER, "responder_app_url"),
        (UserRole.DISPATCHER, "control_center_url"),
        (UserRole.HOSPITAL_OPERATOR, "control_center_url"),
        (UserRole.ADMIN, "control_center_url"),
    ],
)
def test_the_link_points_at_the_app_that_person_uses(
    client: TestClient, make_user, outbox: Outbox, role: UserRole, base_attr: str
) -> None:
    user = make_user(role)
    forgot(client, user.email)
    expected = getattr(SETTINGS, base_attr).rstrip("/")
    assert f"{expected}/reset-password?token=" in outbox.sent[0]["body"]


def test_a_forged_host_header_cannot_redirect_the_link(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.CITIZEN)
    forgot(
        client,
        user.email,
        Host="evil.example",
        **{"X-Forwarded-Host": "evil.example", "Origin": "https://evil.example"},
    )
    assert "evil.example" not in outbox.sent[0]["body"]


def test_the_email_carries_no_operational_data_and_names_the_expiry(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    mail = outbox.sent[0]
    assert "within 30 minutes" in mail["body"]
    assert mail["subject"] == "Reset your RAKSHA NET AI password"
    assert user.email not in mail["subject"]


def test_a_deactivated_account_gets_nothing(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER, is_active=False)
    assert forgot(client, user.email).status_code == 202
    assert outbox.sent == []


def test_an_account_cannot_be_flooded_with_recovery_mail(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    statuses = [forgot(client, user.email).status_code for _ in range(6)]
    assert statuses == [202] * 6
    assert len(outbox.sent) == SETTINGS.password_reset_max_per_hour


def test_a_newer_link_replaces_the_older_one(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    forgot(client, user.email)
    first, second = outbox.token(0), outbox.token(1)
    assert reset(client, first).status_code == 400
    assert reset(client, second).status_code == 200


def test_the_token_is_stored_only_as_a_hash(
    client: TestClient, make_user, outbox: Outbox, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    raw = outbox.token()
    row = db_session.scalars(select(PasswordResetToken)).one()
    assert row.token_hash == hash_refresh_token(raw)
    assert raw not in row.token_hash


# --- completing the reset ----------------------------------------------------------
def test_a_valid_link_sets_the_password_once(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    token = outbox.token()

    response = reset(client, token)
    assert response.status_code == 200, response.text
    assert "access_token" not in response.text  # it does not sign anyone in

    assert login(client, user.email, make_user.password).status_code == 401
    assert login(client, user.email, NEW).status_code == 200
    again = reset(client, token, "another-passphrase-2027")
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "INVALID_RESET_TOKEN"


def test_unknown_expired_and_malformed_links_get_one_answer(
    client: TestClient, make_user, outbox: Outbox, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    token = outbox.token()
    row = db_session.scalars(select(PasswordResetToken)).one()
    row.expires_at = utcnow() - timedelta(minutes=1)
    db_session.flush()

    expired = reset(client, token)
    unknown = reset(client, "x" * 43)
    assert expired.status_code == unknown.status_code == 400
    assert (
        expired.json()["error"]["code"]
        == unknown.json()["error"]["code"]
        == "INVALID_RESET_TOKEN"
    )
    assert reset(client, "short").status_code == 400  # fails validation, same status


def test_a_weak_password_is_refused_without_spending_the_link(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    token = outbox.token()
    weak = reset(client, token, "short")
    assert weak.status_code == 400
    assert weak.json()["error"]["code"] == "WEAK_PASSWORD"
    assert reset(client, token).status_code == 200


def test_a_reset_clears_a_lockout_and_the_forced_change_flag(
    client: TestClient, make_user, outbox: Outbox, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    for _ in range(5):
        login(client, user.email, "wrong-password-wrong")
    assert login(client, user.email, make_user.password).status_code == 403
    user.must_change_password = True
    db_session.flush()

    forgot(client, user.email)
    assert reset(client, outbox.token()).status_code == 200
    ok = login(client, user.email, NEW)
    assert ok.status_code == 200
    assert ok.json()["user"]["must_change_password"] is False


def test_a_reset_ends_every_existing_session(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    session = login(client, user.email, make_user.password).json()
    forgot(client, user.email)
    reset(client, outbox.token())
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}
        ).status_code
        == 401
    )


def test_email_alone_never_gets_past_a_second_factor(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    client.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()})
    client.headers.pop("Authorization")

    forgot(client, user.email)
    assert reset(client, outbox.token()).status_code == 200
    needs_code = login(client, user.email, NEW)
    assert needs_code.status_code == 401
    assert needs_code.json()["error"]["code"] == "MFA_REQUIRED"


def test_the_owner_is_told_their_password_changed(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    reset(client, outbox.token())
    assert [m["subject"] for m in outbox.sent] == [
        "Reset your RAKSHA NET AI password",
        "Your RAKSHA NET AI password was changed",
    ]
    notice = outbox.sent[1]
    assert notice["to"] == user.email
    assert NEW not in notice["body"] and "token=" not in notice["body"]


def test_a_voluntary_change_also_sends_a_notice(
    client: TestClient, make_user, outbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": make_user.password, "new_password": NEW},
    )
    assert response.status_code == 200
    assert outbox.sent[-1]["subject"] == "Your RAKSHA NET AI password was changed"
    assert outbox.sent[-1]["to"] == user.email


def test_requests_and_completions_are_audited_without_secrets(
    client: TestClient, make_user, outbox: Outbox, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    token = outbox.token()
    reset(client, token)
    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action.like("auth.password_reset_%"))
    ).all()
    assert {r.action for r in rows} == {
        "auth.password_reset_requested",
        "auth.password_reset_completed",
    }
    blob = str([r.event_metadata for r in rows]) + str([r.entity_id for r in rows])
    assert token not in blob and NEW not in blob


def test_a_mail_server_outage_does_not_change_the_answer(
    client: TestClient, make_user, monkeypatch
) -> None:
    class Down:
        def send(self, *, recipient: str, title: str, body: str) -> DeliveryOutcome:
            return DeliveryOutcome(DeliveryStatus.FAILED, "down")

    monkeypatch.setattr(SETTINGS, "smtp_host", "mail.test")
    monkeypatch.setattr("app.services.email_service.get_notifier", lambda c, s: Down())
    user = make_user(UserRole.DISPATCHER)
    assert forgot(client, user.email).status_code == 202


def test_a_reset_for_a_user_deactivated_after_asking_is_refused(
    client: TestClient, make_user, outbox: Outbox, db_session: Session
) -> None:
    user: User = make_user(UserRole.DISPATCHER)
    forgot(client, user.email)
    user.is_active = False
    db_session.flush()
    assert reset(client, outbox.token()).status_code == 400
