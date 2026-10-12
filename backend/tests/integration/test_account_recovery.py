"""Administrative recovery: clearing a lockout and resetting a lost second factor."""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.incident import AuditLog
from app.models.user import RefreshToken, User


def authenticate_as(client: TestClient, user: User) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def lock_out(client: TestClient, user: User) -> None:
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "definitely-not-it-xx"},
        )


def enrol(client: TestClient, user: User) -> str:
    authenticate_as(client, user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    client.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()})
    client.headers.pop("Authorization")
    return secret


# --- unlock ------------------------------------------------------------------
def test_an_admin_can_clear_a_lockout(
    client: TestClient, make_user, db_session: Session
) -> None:
    victim = make_user(UserRole.DISPATCHER)
    lock_out(client, victim)
    refused = client.post(
        "/api/v1/auth/login",
        json={"email": victim.email, "password": make_user.password},
    )
    assert refused.status_code == 403

    authenticate_as(client, make_user(UserRole.ADMIN))
    response = client.post(f"/api/v1/users/{victim.id}/unlock")
    assert response.status_code == 200
    client.headers.pop("Authorization")

    ok = client.post(
        "/api/v1/auth/login",
        json={"email": victim.email, "password": make_user.password},
    )
    assert ok.status_code == 200
    audited = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.account_unlocked")
    ).all()
    assert len(audited) == 1


def test_a_dispatcher_cannot_unlock_anyone(client: TestClient, make_user) -> None:
    victim = make_user(UserRole.DISPATCHER)
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    assert client.post(f"/api/v1/users/{victim.id}/unlock").status_code == 403


def test_unlock_requires_authentication(client: TestClient, make_user) -> None:
    victim = make_user(UserRole.DISPATCHER)
    assert client.post(f"/api/v1/users/{victim.id}/unlock").status_code == 401


def test_unlocking_an_unknown_user_is_not_found(client: TestClient, make_user) -> None:
    authenticate_as(client, make_user(UserRole.ADMIN))
    response = client.post("/api/v1/users/00000000-0000-0000-0000-000000000000/unlock")
    assert response.status_code == 404


def test_an_admin_cannot_unlock_a_super_admin(client: TestClient, make_user) -> None:
    boss = make_user(UserRole.SUPER_ADMIN)
    authenticate_as(client, make_user(UserRole.ADMIN))
    assert client.post(f"/api/v1/users/{boss.id}/unlock").status_code == 403


# --- reset MFA ---------------------------------------------------------------
def test_an_admin_can_reset_a_lost_second_factor(
    client: TestClient, make_user, db_session: Session
) -> None:
    user = make_user(UserRole.DISPATCHER)
    enrol(client, user)
    # An existing session, which a reset must end.
    code = pyotp.TOTP(user.mfa_secret).at(__import__("time").time() + 30)
    signed_in = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": make_user.password, "mfa_code": code},
    )
    assert signed_in.status_code == 200

    authenticate_as(client, make_user(UserRole.ADMIN))
    response = client.post(f"/api/v1/users/{user.id}/reset-mfa")
    assert response.status_code == 200
    assert response.json()["mfa_enabled"] is False
    client.headers.pop("Authorization")

    live = db_session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    assert live == []

    # With the second factor gone, the password alone signs in again.
    again = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": make_user.password},
    )
    assert again.status_code == 200
    actions = set(db_session.scalars(select(AuditLog.action)))
    assert "auth.mfa_reset" in actions


def test_an_admin_cannot_reset_their_own_second_factor(
    client: TestClient, make_user
) -> None:
    admin = make_user(UserRole.ADMIN)
    enrol(client, admin)
    authenticate_as(client, admin)
    response = client.post(f"/api/v1/users/{admin.id}/reset-mfa")
    assert response.status_code == 403


def test_a_dispatcher_cannot_reset_mfa(client: TestClient, make_user) -> None:
    victim = make_user(UserRole.DISPATCHER)
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    assert client.post(f"/api/v1/users/{victim.id}/reset-mfa").status_code == 403


def test_reset_mfa_requires_authentication(client: TestClient, make_user) -> None:
    victim = make_user(UserRole.DISPATCHER)
    assert client.post(f"/api/v1/users/{victim.id}/reset-mfa").status_code == 401


def test_an_admin_cannot_reset_a_super_admins_mfa(client: TestClient, make_user) -> None:
    boss = make_user(UserRole.SUPER_ADMIN)
    authenticate_as(client, make_user(UserRole.ADMIN))
    assert client.post(f"/api/v1/users/{boss.id}/reset-mfa").status_code == 403
