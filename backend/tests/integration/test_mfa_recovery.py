"""MFA recovery codes: a lost authenticator must not need an administrator.

An administrator cannot reset their own second factor, so without these a lone
administrator who loses a phone is locked out for good.
"""

from __future__ import annotations

import time

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import recovery_codes
from app.models.enums import UserRole
from app.models.incident import AuditLog
from app.models.user import MfaRecoveryCode, User
from tests.integration.test_mfa_api import authenticate_as, login
from tests.integration.test_password_recovery import SETTINGS, Outbox

NEXT_STEP = 30


@pytest.fixture
def mailbox(monkeypatch) -> Outbox:
    """Email switched on, with sending captured instead of going anywhere."""
    box = Outbox()
    monkeypatch.setattr(SETTINGS, "smtp_host", "mail.test")
    monkeypatch.setattr(
        "app.services.email_service.get_notifier", lambda channel, settings: box
    )
    return box


def enable(client: TestClient, user: User) -> tuple[str, list[str]]:
    """Enrol; return the secret and the recovery codes the response carried."""
    authenticate_as(client, user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    response = client.post(
        "/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}
    )
    assert response.status_code == 200, response.text
    client.headers.pop("Authorization")
    return secret, response.json()["recovery_codes"]


def later_code(secret: str, steps: int = 1) -> str:
    return pyotp.TOTP(secret).at(time.time() + NEXT_STEP * steps)


# --- issuing -------------------------------------------------------------------
def test_enabling_returns_ten_codes_once_and_still_the_user(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    body = client.post(
        "/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}
    ).json()

    assert body["mfa_enabled"] is True and body["email"] == user.email  # still a user
    assert len(body["recovery_codes"]) == 10
    assert len(set(body["recovery_codes"])) == 10
    status = client.get("/api/v1/auth/mfa/recovery-codes").json()
    assert status == {"remaining": 10}  # a count only; the codes are never readable again
    assert "recovery_codes" not in client.get("/api/v1/auth/me").text


def test_only_hashes_are_stored(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    rows = db_session.scalars(
        select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)
    ).all()
    assert len(rows) == 10
    dump = " ".join(row.code_hash for row in rows)
    for code in codes:
        assert recovery_codes.normalise(code) not in dump.upper()
    assert {row.code_hash for row in rows} == {recovery_codes.hash_code(c) for c in codes}


def test_a_failed_confirmation_issues_no_codes(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)
    client.post("/api/v1/auth/mfa/enroll")
    assert (
        client.post("/api/v1/auth/mfa/enable", json={"code": "000000"}).status_code == 400
    )
    assert (
        db_session.scalars(
            select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)
        ).all()
        == []
    )


# --- signing in ---------------------------------------------------------------------
def test_a_recovery_code_signs_in_once_and_only_once(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)

    first = login(client, user, make_user.password, codes[0])
    assert first.status_code == 200, first.text
    assert first.json()["access_token"]

    again = login(client, user, make_user.password, codes[0])
    assert again.status_code == 401
    assert again.json()["error"]["code"] == "INVALID_MFA_CODE"

    # Another code still works.
    assert login(client, user, make_user.password, codes[1]).status_code == 200


def test_typing_it_loosely_is_fine(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    loose = codes[0].replace("-", " ").lower()
    assert login(client, user, make_user.password, loose).status_code == 200


def test_a_wrong_recovery_code_is_refused_and_counts_toward_lockout(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    for _ in range(5):
        login(client, user, make_user.password, "AAAA-BBBB-CCCC")
    db_session.refresh(user)
    assert user.locked_until is not None
    # Locked: even a real code is refused until the lock expires.
    assert login(client, user, make_user.password, codes[0]).status_code == 403


def test_a_code_belonging_to_someone_else_does_not_work(
    client: TestClient, make_user
) -> None:
    alice, bob = make_user(UserRole.DISPATCHER), make_user(UserRole.DISPATCHER)
    _, alice_codes = enable(client, alice)
    enable(client, bob)
    assert login(client, bob, make_user.password, alice_codes[0]).status_code == 401
    # …and Bob's failed attempt did not spend Alice's code.
    assert login(client, alice, make_user.password, alice_codes[0]).status_code == 200


def test_a_recovery_code_does_not_open_an_account_without_the_password(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    assert login(client, user, "not-the-password", codes[0]).status_code == 401


def test_malformed_second_factors_are_validation_errors(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    enable(client, user)
    for code in ("12345", "1234567", "ab", "ABCD-EFGH-JKMN-PQRS-TUVW-XYZA", "<script>"):
        response = login(client, user, make_user.password, code)
        assert response.status_code == 400, code
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_using_a_code_is_audited_without_the_code(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    login(client, user, make_user.password, codes[0])

    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.mfa_recovery_code_used")
    ).all()
    assert len(rows) == 1
    assert rows[0].event_metadata == {"remaining": 9}
    assert recovery_codes.normalise(codes[0]) not in str(rows[0].event_metadata).upper()


# --- everything else a second factor guards ---------------------------------------------
def test_a_recovery_code_can_turn_two_factor_off_when_the_device_is_lost(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    authenticate_as(client, user)

    response = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": make_user.password, "code": codes[0]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["mfa_enabled"] is False
    assert (
        db_session.scalars(
            select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)
        ).all()
        == []
    )  # nothing left to use


def test_a_recovery_code_can_change_the_password(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    authenticate_as(client, user)
    response = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": make_user.password,
            "new_password": "a-different-long-passphrase-7",
            "mfa_code": codes[0],
        },
    )
    assert response.status_code == 200, response.text


def test_regenerating_replaces_the_whole_set(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret, old = enable(client, user)
    authenticate_as(client, user)

    response = client.post(
        "/api/v1/auth/mfa/recovery-codes",
        json={"password": make_user.password, "code": later_code(secret)},
    )
    assert response.status_code == 200, response.text
    new = response.json()["recovery_codes"]
    assert len(new) == 10 and not set(new) & set(old)
    assert client.get("/api/v1/auth/mfa/recovery-codes").json() == {"remaining": 10}

    client.headers.pop("Authorization")
    assert login(client, user, make_user.password, old[0]).status_code == 401
    assert login(client, user, make_user.password, new[0]).status_code == 200


def test_regenerating_needs_the_password_and_a_current_code(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret, codes = enable(client, user)
    authenticate_as(client, user)
    url = "/api/v1/auth/mfa/recovery-codes"

    assert (
        client.post(
            url, json={"password": "wrong", "code": later_code(secret)}
        ).status_code
        == 400
    )
    assert (
        client.post(
            url, json={"password": make_user.password, "code": "000000"}
        ).status_code
        == 400
    )
    assert client.post(url, json={"password": make_user.password}).status_code == 400
    # Nothing changed.
    assert client.get(url).json() == {"remaining": 10}
    client.headers.pop("Authorization")
    assert login(client, user, make_user.password, codes[0]).status_code == 200


def test_the_count_goes_down_as_codes_are_spent(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    for index in range(3):
        assert login(client, user, make_user.password, codes[index]).status_code == 200
    authenticate_as(client, user)
    assert client.get("/api/v1/auth/mfa/recovery-codes").json() == {"remaining": 7}


def test_without_two_factor_there_is_nothing_to_count_or_regenerate(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)
    assert client.get("/api/v1/auth/mfa/recovery-codes").json() == {"remaining": 0}
    refused = client.post(
        "/api/v1/auth/mfa/recovery-codes",
        json={"password": make_user.password, "code": "123456"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "MFA_NOT_ENABLED"


def test_both_endpoints_require_a_login(client: TestClient) -> None:
    assert client.get("/api/v1/auth/mfa/recovery-codes").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/mfa/recovery-codes", json={"password": "x", "code": "123456"}
        ).status_code
        == 401
    )


def test_an_administrators_reset_removes_the_codes(
    client: TestClient, make_user, db_session: Session, as_role
) -> None:
    user = make_user(UserRole.DISPATCHER)
    enable(client, user)
    admin_client, _ = as_role(UserRole.ADMIN)
    assert admin_client.post(f"/api/v1/users/{user.id}/reset-mfa").status_code == 200
    assert (
        db_session.scalars(
            select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)
        ).all()
        == []
    )


def test_enrolling_again_after_turning_it_off_issues_a_fresh_set(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, first = enable(client, user)
    authenticate_as(client, user)
    client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": make_user.password, "code": first[0]},
    )
    _, second = enable(client, user)
    assert len(second) == 10 and not set(first) & set(second)


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPER_ADMIN])
def test_a_lone_administrator_can_recover_their_own_account(
    client: TestClient, make_user, role: UserRole
) -> None:
    """The case that motivated all of this: nobody else can reset an administrator
    who is locked out of their own second factor."""
    admin = make_user(role)
    _, codes = enable(client, admin)
    # The phone is lost: sign in with a recovery code, then replace the factor.
    session = login(client, admin, make_user.password, codes[0])
    assert session.status_code == 200
    client.headers["Authorization"] = f"Bearer {session.json()['access_token']}"
    off = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": make_user.password, "code": codes[1]},
    )
    assert off.status_code == 200 and off.json()["mfa_enabled"] is False


def test_the_owner_is_told_when_a_recovery_code_is_used(
    client: TestClient, make_user, mailbox: Outbox
) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret, codes = enable(client, user)

    # An ordinary authenticator sign-in sends nothing.
    login(client, user, make_user.password, later_code(secret))
    assert mailbox.sent == []

    assert login(client, user, make_user.password, codes[0]).status_code == 200
    assert len(mailbox.sent) == 1
    notice = mailbox.sent[0]
    assert notice["to"] == user.email
    assert notice["subject"] == "A recovery code was used to sign in to RAKSHA NET AI"
    assert "9 unused recovery codes left" in notice["body"]
    assert recovery_codes.normalise(codes[0]) not in notice["body"].upper().replace(
        "-", ""
    )


def test_the_last_code_says_so(client: TestClient, make_user, mailbox: Outbox) -> None:
    user = make_user(UserRole.DISPATCHER)
    _, codes = enable(client, user)
    for code in codes:
        assert login(client, user, make_user.password, code).status_code == 200
    assert "last unused recovery code" in mailbox.sent[-1]["body"]
