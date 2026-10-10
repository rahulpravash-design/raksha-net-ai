"""Changing your own password, and the administrator-set-password lifecycle."""

from __future__ import annotations

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.incident import AuditLog
from app.models.user import RefreshToken, User

NEW = "a-brand-new-passphrase-2026"


def authenticate_as(client: TestClient, user: User) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def change(client: TestClient, current: str, new: str = NEW, **extra: object):
    return client.post(
        "/api/v1/auth/password",
        json={"current_password": current, "new_password": new} | extra,
    )


def login(client: TestClient, email: str, password: str, **extra: object):
    client.headers.pop("Authorization", None)
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password} | extra
    )


# --- the happy path ------------------------------------------------------------
def test_a_user_can_change_their_password(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)

    response = change(client, make_user.password)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["must_change_password"] is False

    assert login(client, user.email, make_user.password).status_code == 401
    assert login(client, user.email, NEW).status_code == 200

    audited = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.password_changed")
    ).all()
    assert len(audited) == 1
    assert NEW not in str(audited[0].event_metadata) and make_user.password not in str(
        audited[0].event_metadata
    )


def test_the_callers_session_continues_and_every_other_one_ends(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    other_session = login(client, user.email, make_user.password).json()
    authenticate_as(client, user)

    new_tokens = change(client, make_user.password).json()

    # Exactly one live refresh token remains: the caller's new one.
    live = db_session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    assert len(live) == 1

    client.headers.pop("Authorization")
    fresh = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert fresh.status_code == 200
    # The other sign-in's token is dead (and, as for any replayed revoked token,
    # presenting it ends the chain — that is the designed compromise response).
    old = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": other_session["refresh_token"]}
    )
    assert old.status_code == 401


# --- refusals --------------------------------------------------------------------
def test_a_wrong_current_password_is_refused_with_400_not_401(
    client: TestClient, make_user
) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    response = change(client, "not-my-password-at-all")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_wrong_current_passwords_count_toward_lockout(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)
    for _ in range(5):
        change(client, "guess-guess-guess-guess")
    client.headers.pop("Authorization")
    locked = login(client, user.email, make_user.password)
    assert locked.status_code == 403
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_a_weak_new_password_is_refused_and_nothing_changes(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    authenticate_as(client, user)
    response = change(client, make_user.password, new="short")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"
    assert login(client, user.email, make_user.password).status_code == 200


def test_the_new_password_must_differ_from_the_old_one(
    client: TestClient, make_user
) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    response = change(client, make_user.password, new=make_user.password)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PASSWORD_UNCHANGED"


def test_changing_a_password_requires_authentication(client: TestClient) -> None:
    assert change(client, "x", NEW).status_code == 401


def test_a_malformed_body_is_a_validation_error(client: TestClient, make_user) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    response = client.post("/api/v1/auth/password", json={"new_password": NEW})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- MFA -------------------------------------------------------------------------
def enrol(client: TestClient, user: User) -> str:
    authenticate_as(client, user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    client.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()})
    return secret


def test_with_mfa_on_a_current_code_is_also_required(
    client: TestClient, make_user
) -> None:
    user = make_user(UserRole.DISPATCHER)
    secret = enrol(client, user)

    missing = change(client, make_user.password)
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INVALID_MFA_CODE"

    wrong = change(client, make_user.password, mfa_code="000000")
    assert wrong.status_code == 400

    # A code from a later step than the one used to enable MFA.
    totp = pyotp.TOTP(secret)
    code = totp.at(totp.timecode(__import__("datetime").datetime.now()) * 30 + 30)
    ok = change(client, make_user.password, mfa_code=code)
    assert ok.status_code == 200, ok.text


def test_a_code_cannot_be_replayed_to_change_the_password_twice(
    client: TestClient, make_user
) -> None:
    import datetime

    user = make_user(UserRole.DISPATCHER)
    secret = enrol(client, user)
    totp = pyotp.TOTP(secret)
    code = totp.at(datetime.datetime.now() + datetime.timedelta(seconds=30))
    assert change(client, make_user.password, mfa_code=code).status_code == 200
    assert (
        change(client, NEW, new="yet-another-passphrase-2027", mfa_code=code).status_code
        == 400
    )


# --- administrator-set passwords --------------------------------------------------
def create_as_admin(client: TestClient, make_user, email: str = "fresh@example.com"):
    authenticate_as(client, make_user(UserRole.ADMIN))
    response = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "full_name": "Fresh Operator",
            "password": "admin-chosen-passphrase-1",
            "role": "DISPATCHER",
        },
    )
    assert response.status_code == 201, response.text
    client.headers.pop("Authorization")
    return response.json()


def test_an_account_created_by_an_admin_must_change_its_password(
    client: TestClient, make_user
) -> None:
    body = create_as_admin(client, make_user)
    assert body["must_change_password"] is True

    session = login(client, "fresh@example.com", "admin-chosen-passphrase-1")
    assert session.status_code == 200
    assert session.json()["user"]["must_change_password"] is True


def test_until_it_is_changed_everything_else_is_refused(
    client: TestClient, make_user
) -> None:
    create_as_admin(client, make_user)
    token = login(client, "fresh@example.com", "admin-chosen-passphrase-1").json()[
        "access_token"
    ]
    client.headers["Authorization"] = f"Bearer {token}"

    blocked = client.get("/api/v1/incidents")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/v1/notifications/unread-count").status_code == 403

    # What a person needs in order to satisfy the policy stays open.
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/mfa/enroll").status_code == 200

    changed = change(client, "admin-chosen-passphrase-1")
    assert changed.status_code == 200
    client.headers["Authorization"] = f"Bearer {changed.json()['access_token']}"
    assert client.get("/api/v1/incidents").status_code == 200
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is False


def test_self_registered_and_seeded_accounts_are_not_forced(
    client: TestClient, make_user
) -> None:
    assert make_user(UserRole.DISPATCHER).must_change_password is False


# --- admin reset ------------------------------------------------------------------
def test_an_admin_can_set_a_temporary_password_for_someone_locked_out(
    client: TestClient, make_user, db_session: Session
) -> None:
    victim = make_user(UserRole.DISPATCHER)
    for _ in range(5):
        login(client, victim.email, "wrong-password-wrong")
    old_session = None
    authenticate_as(client, make_user(UserRole.ADMIN))

    response = client.post(
        f"/api/v1/users/{victim.id}/reset-password",
        json={"new_password": "temporary-passphrase-abc"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["must_change_password"] is True
    assert body["locked_until"] is None and body["failed_login_attempts"] == 0
    assert old_session is None

    assert login(client, victim.email, make_user.password).status_code == 401
    assert login(client, victim.email, "temporary-passphrase-abc").status_code == 200
    audited = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.password_reset_by_admin")
    ).all()
    assert len(audited) == 1
    assert "temporary-passphrase-abc" not in str(audited[0].event_metadata)


def test_a_reset_ends_the_users_existing_sessions(client: TestClient, make_user) -> None:
    victim = make_user(UserRole.DISPATCHER)
    session = login(client, victim.email, make_user.password).json()
    authenticate_as(client, make_user(UserRole.ADMIN))
    client.post(
        f"/api/v1/users/{victim.id}/reset-password",
        json={"new_password": "temporary-passphrase-abc"},
    )
    client.headers.pop("Authorization")
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}
        ).status_code
        == 401
    )


def test_a_reset_is_subject_to_the_password_rules(client: TestClient, make_user) -> None:
    victim = make_user(UserRole.DISPATCHER)
    authenticate_as(client, make_user(UserRole.ADMIN))
    response = client.post(
        f"/api/v1/users/{victim.id}/reset-password", json={"new_password": "short"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"


def test_an_admin_cannot_reset_their_own_password_this_way(
    client: TestClient, make_user
) -> None:
    admin = make_user(UserRole.ADMIN)
    authenticate_as(client, admin)
    response = client.post(
        f"/api/v1/users/{admin.id}/reset-password",
        json={"new_password": "temporary-passphrase-abc"},
    )
    assert response.status_code == 403


def test_only_a_super_admin_may_reset_a_super_admin(
    client: TestClient, make_user
) -> None:
    target = make_user(UserRole.SUPER_ADMIN)
    authenticate_as(client, make_user(UserRole.ADMIN))
    response = client.post(
        f"/api/v1/users/{target.id}/reset-password",
        json={"new_password": "temporary-passphrase-abc"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "role",
    [
        UserRole.CITIZEN,
        UserRole.RESPONDER,
        UserRole.DISPATCHER,
        UserRole.HOSPITAL_OPERATOR,
    ],
)
def test_only_administrators_can_reset_passwords(
    as_role, make_user, role: UserRole
) -> None:
    client, _ = as_role(role)
    victim = make_user(UserRole.DISPATCHER)
    response = client.post(
        f"/api/v1/users/{victim.id}/reset-password",
        json={"new_password": "temporary-passphrase-abc"},
    )
    assert response.status_code == 403


def test_resetting_an_unknown_user_is_a_404(as_role) -> None:
    import uuid

    client, _ = as_role(UserRole.ADMIN)
    response = client.post(
        f"/api/v1/users/{uuid.uuid4()}/reset-password",
        json={"new_password": "temporary-passphrase-abc"},
    )
    assert response.status_code == 404


def test_the_reset_endpoint_requires_authentication(client: TestClient) -> None:
    import uuid

    response = client.post(
        f"/api/v1/users/{uuid.uuid4()}/reset-password",
        json={"new_password": "temporary-passphrase-abc"},
    )
    assert response.status_code == 401
