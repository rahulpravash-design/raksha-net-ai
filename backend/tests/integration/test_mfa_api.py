"""TOTP MFA: enrolment, login, replay, lockout interaction and enforcement."""

from __future__ import annotations

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.incident import AuditLog
from app.models.user import User


def authenticate_as(client: TestClient, user: User) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def enrol(client: TestClient, user: User) -> str:
    """Enrol and confirm MFA for ``user``; return the shared secret."""
    authenticate_as(client, user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    confirmed = client.post(
        "/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}
    )
    assert confirmed.status_code == 200, confirmed.text
    client.headers.pop("Authorization")
    return secret


def login(client: TestClient, user: User, password: str, code: str | None = None):
    body = {"email": user.email, "password": password}
    if code is not None:
        body["mfa_code"] = code
    return client.post("/api/v1/auth/login", json=body)


# --- enrolment ---------------------------------------------------------------
def test_enrolment_returns_a_secret_but_does_not_enable_mfa(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)
    body = client.post("/api/v1/auth/mfa/enroll").json()

    assert body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://totp/")
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is False


def test_enabling_needs_a_valid_code(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)
    client.post("/api/v1/auth/mfa/enroll")

    bad = client.post("/api/v1/auth/mfa/enable", json={"code": "000000"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "INVALID_MFA_CODE"
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is False


def test_enabling_without_enrolling_first_is_refused(
    client: TestClient, make_user
) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    response = client.post("/api/v1/auth/mfa/enable", json={"code": "123456"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MFA_NOT_ENROLLING"


def test_a_malformed_code_is_a_validation_error(client: TestClient, make_user) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    response = client.post("/api/v1/auth/mfa/enable", json={"code": "12ab"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_enrolment_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/v1/auth/mfa/enroll").status_code == 401
    assert (
        client.post("/api/v1/auth/mfa/enable", json={"code": "123456"}).status_code == 401
    )
    assert (
        client.post(
            "/api/v1/auth/mfa/disable", json={"code": "123456", "password": "x"}
        ).status_code
        == 401
    )


def test_enrolling_twice_after_enabling_is_a_conflict(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    enrol(client, user)
    authenticate_as(client, user)
    response = client.post("/api/v1/auth/mfa/enroll")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MFA_ALREADY_ENABLED"


def test_the_secret_is_encrypted_at_rest(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret = enrol(client, user)
    stored = db_session.execute(
        text("SELECT mfa_secret FROM users WHERE id = :id"), {"id": user.id}
    ).scalar_one()
    assert secret not in stored
    assert stored.startswith("gAAAA")


# --- login -------------------------------------------------------------------
def test_login_without_mfa_is_unchanged(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    assert login(client, user, make_user.password).status_code == 200


def test_login_with_mfa_demands_a_code(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    enrol(client, user)

    response = login(client, user, make_user.password)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MFA_REQUIRED"
    assert "access_token" not in response.text


def test_login_with_the_right_code_succeeds(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret = enrol(client, user)
    # Enabling consumed this step, so use the next one — the replay rule at work.
    code = pyotp.TOTP(secret).at(__import__("time").time() + 30)
    response = login(client, user, make_user.password, code)
    assert response.status_code == 200
    assert response.json()["user"]["mfa_enabled"] is True


def test_login_with_a_wrong_code_is_refused(client: TestClient, make_user) -> None:
    user = make_user(UserRole.DISPATCHER)
    enrol(client, user)
    response = login(client, user, make_user.password, "000000")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_MFA_CODE"


def test_a_code_that_was_just_used_cannot_be_used_again(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret = enrol(client, user)
    code = pyotp.TOTP(secret).at(__import__("time").time() + 30)

    assert login(client, user, make_user.password, code).status_code == 200
    replay = login(client, user, make_user.password, code)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "INVALID_MFA_CODE"


def test_the_right_code_with_the_wrong_password_gets_nothing(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret = enrol(client, user)
    code = pyotp.TOTP(secret).at(__import__("time").time() + 30)
    response = login(client, user, "not-the-right-password", code)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_guessing_codes_locks_the_account(
    client: TestClient, make_user, db_session: Session
) -> None:
    """With the password known, the code is all that is left to guess."""
    user = make_user(UserRole.DISPATCHER)
    enrol(client, user)

    codes = [f"{n:06d}" for n in range(1, 6)]
    responses = [login(client, user, make_user.password, c) for c in codes]
    assert [r.status_code for r in responses[:4]] == [401] * 4
    assert responses[4].status_code == 403
    assert responses[4].json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_a_missing_code_does_not_count_toward_lockout(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    enrol(client, user)
    for _ in range(8):
        assert login(client, user, make_user.password).status_code == 401
    # Still not locked: the second attempt below reaches the MFA prompt.
    assert (
        login(client, user, make_user.password).json()["error"]["code"] == "MFA_REQUIRED"
    )


# --- disabling ---------------------------------------------------------------
def test_disabling_needs_the_password_and_a_current_code(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret = enrol(client, user)
    authenticate_as(client, user)
    code = pyotp.TOTP(secret).at(__import__("time").time() + 30)

    wrong_password = client.post(
        "/api/v1/auth/mfa/disable", json={"password": "not-the-password", "code": code}
    )
    assert wrong_password.status_code == 400

    wrong_code = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": make_user.password, "code": "000000"},
    )
    assert wrong_code.status_code == 400
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is True

    ok = client.post(
        "/api/v1/auth/mfa/disable", json={"password": make_user.password, "code": code}
    )
    assert ok.status_code == 200
    assert ok.json()["mfa_enabled"] is False


def test_disabling_when_not_enabled_is_a_conflict(client: TestClient, make_user) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    response = client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": make_user.password, "code": "123456"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MFA_NOT_ENABLED"


def test_mfa_changes_are_audited(
    client: TestClient, make_user, db_session: Session
) -> None:
    enrol(client, make_user(UserRole.DISPATCHER))
    actions = set(
        db_session.scalars(
            select(AuditLog.action).where(AuditLog.action.like("auth.mfa_%"))
        )
    )
    assert actions == {"auth.mfa_enrollment_started", "auth.mfa_enabled"}


# --- enforcement for operational roles ---------------------------------------
@pytest.fixture
def mfa_enforced(monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_required_for_operational", True)


def test_an_operational_user_without_mfa_is_blocked_when_enforced(
    client: TestClient, make_user, mfa_enforced
) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    response = client.get("/api/v1/incidents")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "MFA_ENROLLMENT_REQUIRED"


def test_a_blocked_user_can_still_reach_me_and_enrol(
    client: TestClient, make_user, mfa_enforced
) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/mfa/enroll").status_code == 200


def test_an_enrolled_operational_user_is_let_through_when_enforced(
    client: TestClient, make_user, mfa_enforced
) -> None:
    user = make_user(UserRole.DISPATCHER)
    enrol(client, user)
    authenticate_as(client, user)
    assert client.get("/api/v1/incidents").status_code == 200


def test_enforcement_does_not_touch_citizens(
    client: TestClient, make_user, mfa_enforced
) -> None:
    authenticate_as(client, make_user(UserRole.CITIZEN))
    assert client.get("/api/v1/incidents/mine").status_code == 200


def test_enforcement_is_off_by_default(client: TestClient, make_user) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    assert client.get("/api/v1/incidents").status_code == 200
