"""The first-administrator bootstrap: when it may run, what it creates, what it leaves.

A new deployment has no administrator, and only an administrator can create one over
the API, so ``BootstrapService`` / ``app.cli.create_first_admin`` is the way in. The
tests below pin the rules that keep it from becoming a way to mint administrators later.
"""

from __future__ import annotations

import contextlib
import io
import threading
from contextlib import nullcontext

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.cli import create_first_admin as cli
from app.core.config import get_settings
from app.core.errors import (
    AdminAlreadyExistsError,
    EmailAlreadyRegisteredError,
    WeakPasswordError,
)
from app.core.security import verify_password
from app.models.enums import UserRole
from app.models.incident import AuditLog
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import FirstAdminCreate
from app.services.audit_service import AuditAction
from app.services.bootstrap_service import BootstrapService

EMAIL = "founder@example.org"
PASSWORD = "a-long-enough-passphrase"
NEW_PASSWORD = "a-different-long-passphrase"


def payload(email: str = EMAIL, password: str = PASSWORD) -> FirstAdminCreate:
    return FirstAdminCreate(
        email=email, full_name="Founding Administrator", password=password
    )


def count(session: Session, *conditions) -> int:
    return session.scalar(select(func.count()).select_from(User).where(*conditions)) or 0


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- what it creates ---------------------------------------------------------
def test_it_creates_a_super_admin_who_must_choose_a_new_password(
    db_session: Session,
) -> None:
    user = BootstrapService(db_session).create_first_admin(payload())

    assert user.role is UserRole.SUPER_ADMIN
    assert user.is_active
    assert user.must_change_password
    assert not user.mfa_enabled
    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password)


def test_the_creation_is_audited_and_the_audit_row_holds_no_password(
    db_session: Session,
) -> None:
    user = BootstrapService(db_session).create_first_admin(payload())

    rows = db_session.scalars(select(AuditLog)).all()
    assert [row.action for row in rows] == [AuditAction.FIRST_ADMIN_CREATED]
    row = rows[0]
    assert row.actor_id is None  # no signed-in actor exists yet
    assert row.entity_id == str(user.id)
    assert row.event_metadata == {"role": "SUPER_ADMIN", "via": "cli"}
    assert PASSWORD not in repr(row.event_metadata)


# --- when it may run ---------------------------------------------------------
@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPER_ADMIN])
@pytest.mark.parametrize("is_active", [True, False])
def test_it_refuses_once_any_administrator_exists(
    db_session: Session, make_user, role: UserRole, is_active: bool
) -> None:
    """Active or not: a deactivated administrator is still an administrator."""
    make_user(role, is_active=is_active)

    with pytest.raises(AdminAlreadyExistsError):
        BootstrapService(db_session).create_first_admin(payload())

    assert count(db_session, User.email == EMAIL) == 0


def test_other_roles_do_not_stand_in_the_way(db_session: Session, make_user) -> None:
    for role in (
        UserRole.CITIZEN,
        UserRole.DISPATCHER,
        UserRole.RESPONDER,
        UserRole.HOSPITAL_OPERATOR,
    ):
        make_user(role)

    assert BootstrapService(db_session).create_first_admin(payload()).role is (
        UserRole.SUPER_ADMIN
    )


def test_it_cannot_be_used_twice(db_session: Session) -> None:
    service = BootstrapService(db_session)
    service.create_first_admin(payload())

    with pytest.raises(AdminAlreadyExistsError):
        service.create_first_admin(payload(email="second@example.org"))

    assert count(db_session, User.role == UserRole.SUPER_ADMIN) == 1


def test_an_existing_account_is_not_promoted_by_reusing_its_email(
    db_session: Session, make_user
) -> None:
    citizen = make_user(UserRole.CITIZEN, email=EMAIL)

    with pytest.raises(EmailAlreadyRegisteredError):
        BootstrapService(db_session).create_first_admin(payload())

    db_session.refresh(citizen)
    assert citizen.role is UserRole.CITIZEN
    assert count(db_session, User.role.in_((UserRole.ADMIN, UserRole.SUPER_ADMIN))) == 0


def test_a_weak_password_creates_nothing(db_session: Session) -> None:
    with pytest.raises(WeakPasswordError):
        BootstrapService(db_session).create_first_admin(payload(password="short"))

    assert count(db_session) == 0
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_two_simultaneous_runs_create_exactly_one_administrator(engine, monkeypatch):
    """Two real connections race. A barrier holds both between "no administrator
    exists" and the insert; only the advisory lock keeps the second one out of that gap,
    so without the lock both would be created."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    gap = threading.Barrier(2)
    original = UserRepository.email_exists

    def email_exists_in_the_gap(self: UserRepository, email: str) -> bool:
        # With the lock, the other run is still waiting outside, so this times out.
        with contextlib.suppress(threading.BrokenBarrierError):
            gap.wait(timeout=1.5)
        return original(self, email)

    monkeypatch.setattr(UserRepository, "email_exists", email_exists_in_the_gap)

    emails = ["racer1@example.org", "racer2@example.org"]
    outcomes: list[object] = []

    def run(email: str) -> None:
        with factory() as session:
            try:
                outcomes.append(
                    BootstrapService(session).create_first_admin(payload(email))
                )
            except Exception as exc:  # recorded and asserted on below
                outcomes.append(exc)

    threads = [threading.Thread(target=run, args=(email,)) for email in emails]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(type(o).__name__ for o in outcomes) == [
            "AdminAlreadyExistsError",
            "User",
        ], outcomes
    finally:
        with engine.begin() as connection:  # these rows were really committed
            connection.execute(
                delete(AuditLog).where(AuditLog.action == AuditAction.FIRST_ADMIN_CREATED)
            )
            connection.execute(delete(User).where(User.email.in_(emails)))


# --- the first sign-in -------------------------------------------------------
def sign_in(client: TestClient, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_first_admin_changes_the_password_and_can_then_administer(
    client: TestClient, db_session: Session
) -> None:
    BootstrapService(db_session).create_first_admin(payload())

    token = sign_in(client, PASSWORD)["access_token"]
    blocked = client.get("/api/v1/users", headers=bearer(token))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = client.post(
        "/api/v1/auth/password",
        headers=bearer(token),
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text

    headers = bearer(sign_in(client, NEW_PASSWORD)["access_token"])
    assert client.get("/api/v1/users", headers=headers).status_code == 200
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "dispatcher@example.org",
            "full_name": "First Dispatcher",
            "password": "yet-another-long-passphrase",
            "role": "DISPATCHER",
        },
    )
    assert created.status_code == 201, created.text


def test_where_mfa_is_required_the_first_admin_must_enrol_before_administering(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "mfa_required_for_operational", True)
    BootstrapService(db_session).create_first_admin(payload())

    token = sign_in(client, PASSWORD)["access_token"]
    token = client.post(
        "/api/v1/auth/password",
        headers=bearer(token),
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    ).json()["access_token"]

    blocked = client.get("/api/v1/users", headers=bearer(token))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "MFA_ENROLLMENT_REQUIRED"

    secret = client.post("/api/v1/auth/mfa/enroll", headers=bearer(token)).json()[
        "secret"
    ]
    enabled = client.post(
        "/api/v1/auth/mfa/enable",
        headers=bearer(token),
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert enabled.status_code == 200, enabled.text
    assert client.get("/api/v1/users", headers=bearer(token)).status_code == 200


def test_there_is_no_http_route_for_it(client: TestClient) -> None:
    """The bootstrap is a shell command. A route would be a setup page anyone could
    find and race."""
    paths = [getattr(route, "path", "") for route in client.app.routes]
    assert not [p for p in paths if "bootstrap" in p.lower() or "first" in p.lower()]


# --- the command -------------------------------------------------------------
def test_the_command_creates_the_admin_and_then_refuses(
    db_session: Session, monkeypatch, capsys
) -> None:
    argv = ["--email", EMAIL, "--name", "Founding Administrator", "--password-stdin"]
    opener = lambda: nullcontext(db_session)  # noqa: E731

    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(argv, open_session=opener) == cli.EXIT_CREATED
    first = capsys.readouterr()
    assert EMAIL in first.out
    assert PASSWORD not in first.out + first.err
    assert count(db_session, User.role == UserRole.SUPER_ADMIN) == 1

    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(argv, open_session=opener) == cli.EXIT_REFUSED
    second = capsys.readouterr()
    assert "already exists" in second.err
    assert PASSWORD not in second.out + second.err
    assert count(db_session, User.role == UserRole.SUPER_ADMIN) == 1
