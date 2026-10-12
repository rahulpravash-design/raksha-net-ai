"""Authentication endpoints against a live database."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.incident import AuditLog
from app.models.user import RefreshToken, User

REGISTRATION = {
    "email": "Asha.R@example.org",
    "password": "correct-horse-battery-staple",
    "full_name": "Asha R",
    "phone": "+91 98765 43210",
}


def register(client: TestClient, **overrides: object) -> dict:
    payload = REGISTRATION | overrides
    return client.post("/api/v1/auth/register", json=payload).json()


# --- registration ------------------------------------------------------------
def test_registration_creates_a_citizen(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == UserRole.CITIZEN.value
    assert body["email"] == "asha.r@example.org"  # normalised
    assert body["phone"] == "+919876543210"  # normalised
    assert "hashed_password" not in body
    assert "password" not in body


def test_registration_cannot_grant_itself_a_role(client: TestClient) -> None:
    """A ``role`` in the body is ignored rather than honoured."""
    response = client.post("/api/v1/auth/register", json=REGISTRATION | {"role": "ADMIN"})
    assert response.status_code == 201
    assert response.json()["role"] == UserRole.CITIZEN.value


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=REGISTRATION)
    response = client.post(
        "/api/v1/auth/register", json=REGISTRATION | {"email": "ASHA.R@example.org"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_a_weak_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json=REGISTRATION | {"password": "short"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"


def test_an_invalid_email_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json=REGISTRATION | {"email": "not-an-email"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- login -------------------------------------------------------------------
def test_login_returns_a_token_pair(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=REGISTRATION)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTRATION["email"], "password": REGISTRATION["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0
    assert body["user"]["email"] == "asha.r@example.org"


def test_unknown_email_and_wrong_password_are_indistinguishable(
    client: TestClient,
) -> None:
    """The endpoint must not be a user-enumeration oracle."""
    client.post("/api/v1/auth/register", json=REGISTRATION)

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTRATION["email"], "password": "not-the-right-password"},
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.org", "password": "not-the-right-password"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["error"]["code"] == unknown_email.json()["error"]["code"]
    assert (
        wrong_password.json()["error"]["message"]
        == unknown_email.json()["error"]["message"]
    )


def test_a_deactivated_account_cannot_sign_in(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.CITIZEN, is_active=False)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": make_user.password},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_a_failed_login_is_audited(client: TestClient, db_session: Session) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.org", "password": "whatever-this-is"},
    )
    entries = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.login_failed")
    ).all()
    assert len(entries) == 1
    assert "password" not in str(entries[0].event_metadata)


# --- current user ------------------------------------------------------------
def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_me_returns_the_caller(as_role) -> None:
    client, user = as_role(UserRole.DISPATCHER)
    body = client.get("/api/v1/auth/me").json()
    assert body["id"] == str(user.id)
    assert body["role"] == "DISPATCHER"


def test_a_garbage_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_a_refresh_token_cannot_be_used_as_a_bearer_credential(
    client: TestClient,
) -> None:
    client.post("/api/v1/auth/register", json=REGISTRATION)
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTRATION["email"], "password": REGISTRATION["password"]},
    ).json()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert response.status_code == 401


def test_a_user_deactivated_mid_session_loses_access_immediately(
    client: TestClient, make_user, db_session: Session
) -> None:
    """Access is checked against the database, not trusted from the token."""
    user = make_user(UserRole.CITIZEN)
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": make_user.password},
    ).json()

    user.is_active = False
    db_session.commit()

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 403


# --- refresh rotation --------------------------------------------------------
def _login(client: TestClient, user: User, password: str) -> dict:
    return client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": password}
    ).json()


def test_refresh_rotates_both_tokens(client: TestClient, make_user) -> None:
    user = make_user(UserRole.CITIZEN)
    first = _login(client, user, make_user.password)

    second = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]


def test_a_rotated_refresh_token_is_revoked(client: TestClient, make_user) -> None:
    user = make_user(UserRole.CITIZEN)
    first = _login(client, user, make_user.password)
    client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})

    replay = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert replay.status_code == 401


def test_replaying_a_revoked_token_ends_every_session(
    client: TestClient, make_user, db_session: Session
) -> None:
    """Replay is the signature of a stolen credential, so the whole chain goes."""
    user = make_user(UserRole.CITIZEN)
    first = _login(client, user, make_user.password)
    second = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    ).json()

    client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})

    still_usable = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
    )
    assert still_usable.status_code == 401

    live_tokens = db_session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    assert live_tokens == []

    # Two detections: the deliberate replay, then the now-revoked successor.
    # Each presentation of a revoked token is itself a reuse event.
    audited = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.token_reuse_detected")
    ).all()
    assert len(audited) == 2


def test_an_unknown_refresh_token_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 64})
    assert response.status_code == 401


# --- logout ------------------------------------------------------------------
def test_logout_revokes_the_refresh_token(client: TestClient, make_user) -> None:
    user = make_user(UserRole.CITIZEN)
    tokens = _login(client, user, make_user.password)

    assert (
        client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 200
    )

    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )


def test_logout_is_idempotent(client: TestClient, make_user) -> None:
    """Signing out twice is not an error worth surfacing to a user."""
    user = make_user(UserRole.CITIZEN)
    tokens = _login(client, user, make_user.password)
    client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert (
        client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 200
    )


# --- account lockout ---------------------------------------------------------
def _wrong_login(client: TestClient, email: str):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": "not-the-password-xx"}
    )


def test_repeated_failures_lock_the_account(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.CITIZEN)

    for _ in range(4):
        assert _wrong_login(client, user.email).status_code == 401

    fifth = _wrong_login(client, user.email)
    assert fifth.status_code == 403
    body = fifth.json()["error"]
    assert body["code"] == "ACCOUNT_LOCKED"
    assert body["details"]["retry_after_seconds"] > 0

    db_session.refresh(user)
    assert user.locked_until is not None
    audited = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.account_locked")
    ).all()
    assert len(audited) == 1


def test_a_locked_account_refuses_even_the_correct_password(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.CITIZEN)
    for _ in range(5):
        _wrong_login(client, user.email)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": make_user.password},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_a_lock_expires(client: TestClient, make_user, db_session: Session) -> None:
    from datetime import timedelta

    from app.utils.time import utcnow

    user = make_user(UserRole.CITIZEN)
    for _ in range(5):
        _wrong_login(client, user.email)

    user.locked_until = utcnow() - timedelta(seconds=1)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": make_user.password},
    )
    assert response.status_code == 200
    db_session.refresh(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_a_successful_login_resets_the_failure_count(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.CITIZEN)
    for _ in range(3):
        _wrong_login(client, user.email)
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": make_user.password},
        ).status_code
        == 200
    )

    # Three more failures would lock a stale count of 6, but not a fresh 3.
    for _ in range(3):
        assert _wrong_login(client, user.email).status_code == 401


def test_lockout_backs_off_progressively(
    client: TestClient, make_user, db_session: Session
) -> None:
    from datetime import timedelta

    from app.utils.time import utcnow

    user = make_user(UserRole.CITIZEN)
    for _ in range(5):
        _wrong_login(client, user.email)
    db_session.refresh(user)
    first_lock = user.locked_until - utcnow()

    user.locked_until = utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert _wrong_login(client, user.email).status_code == 403
    db_session.refresh(user)
    second_lock = user.locked_until - utcnow()

    assert second_lock > first_lock * 1.5


def test_an_unknown_email_cannot_be_locked(client: TestClient) -> None:
    for _ in range(8):
        response = _wrong_login(client, "nobody@example.org")
        assert response.status_code == 401
