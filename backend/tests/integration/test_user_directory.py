"""The admin user view shows lockout state; dispatchers get a narrow responder lookup."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.enums import UserRole
from app.utils.time import utcnow


def test_the_admin_list_shows_who_is_locked(as_role, make_user, db_session) -> None:
    locked = make_user(UserRole.DISPATCHER, email="locked@example.com")
    locked.locked_until = utcnow() + timedelta(minutes=10)
    locked.failed_login_attempts = 5
    db_session.flush()
    client, _ = as_role(UserRole.ADMIN)

    body = client.get("/api/v1/users", params={"q": "locked@example.com"}).json()
    row = body["items"][0]
    assert row["locked_until"] is not None
    assert row["failed_login_attempts"] == 5


def test_the_self_view_does_not_carry_lockout_fields(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    body = client.get("/api/v1/users/me").json()
    assert "locked_until" not in body
    assert "failed_login_attempts" not in body


def test_the_directory_lists_only_active_responders_with_minimal_fields(
    as_role, make_user
) -> None:
    make_user(UserRole.RESPONDER, email="crew1@example.com", full_name="Crew One")
    make_user(UserRole.RESPONDER, email="gone@example.com", is_active=False)
    make_user(UserRole.HOSPITAL_OPERATOR, email="hosp@example.com")
    make_user(UserRole.DISPATCHER, email="disp@example.com")
    client, _ = as_role(UserRole.DISPATCHER)

    rows = client.get("/api/v1/users/directory").json()
    assert rows, "the active responder must be listed"
    assert all(set(row) == {"id", "full_name", "role"} for row in rows)
    assert {row["role"] for row in rows} == {"RESPONDER"}
    assert "Crew One" in {row["full_name"] for row in rows}
    assert "gone@example.com" not in str(rows)


def test_the_directory_can_be_searched(as_role, make_user) -> None:
    make_user(UserRole.RESPONDER, email="alpha@example.com", full_name="Alpha Crew")
    make_user(UserRole.RESPONDER, email="bravo@example.com", full_name="Bravo Crew")
    client, _ = as_role(UserRole.DISPATCHER)
    names = {
        row["full_name"]
        for row in client.get("/api/v1/users/directory", params={"q": "alpha"}).json()
    }
    assert names == {"Alpha Crew"}


@pytest.mark.parametrize(
    "role", [UserRole.CITIZEN, UserRole.RESPONDER, UserRole.HOSPITAL_OPERATOR]
)
def test_the_directory_is_closed_to_non_dispatch_roles(as_role, role: UserRole) -> None:
    client, _ = as_role(role)
    assert client.get("/api/v1/users/directory").status_code == 403


def test_the_directory_requires_authentication(client) -> None:
    assert client.get("/api/v1/users/directory").status_code == 401
