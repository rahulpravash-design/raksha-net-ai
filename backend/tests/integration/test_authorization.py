"""The role x endpoint authorisation matrix.

``docs/TESTING.md`` section 2 requires every endpoint to be covered for the
wrong-role and wrong-owner cases. This module is that coverage.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.enums import UserRole

NON_OPERATIONAL = [UserRole.CITIZEN]
NON_DISPATCH = [UserRole.CITIZEN, UserRole.RESPONDER, UserRole.HOSPITAL_OPERATOR]
NON_ADMIN = [
    UserRole.CITIZEN,
    UserRole.RESPONDER,
    UserRole.DISPATCHER,
    UserRole.HOSPITAL_OPERATOR,
]


def make_incident(authed_client, make_user, incident_payload) -> dict:
    response = authed_client(make_user(UserRole.CITIZEN)).post(
        "/api/v1/incidents", json=incident_payload
    )
    assert response.status_code == 201
    return response.json()


# --- unauthenticated ---------------------------------------------------------
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/users/me"),
        ("get", "/api/v1/users"),
        ("get", "/api/v1/incidents"),
        ("get", "/api/v1/incidents/mine"),
        ("post", "/api/v1/incidents"),
        ("get", "/api/v1/incidents/stats/summary"),
        ("get", "/api/v1/geo/incidents/nearby"),
        ("get", "/api/v1/geo/incidents/bbox"),
    ],
)
def test_every_protected_endpoint_requires_authentication(
    client: TestClient, method: str, path: str
) -> None:
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401, path


# --- operational-only endpoints ----------------------------------------------
@pytest.mark.parametrize("role", NON_OPERATIONAL)
def test_the_queue_is_closed_to_non_operational_roles(as_role, role: UserRole) -> None:
    client, _ = as_role(role)
    assert client.get("/api/v1/incidents").status_code == 403


@pytest.mark.parametrize("role", NON_OPERATIONAL)
def test_geo_endpoints_are_closed_to_non_operational_roles(
    as_role, role: UserRole
) -> None:
    client, _ = as_role(role)
    nearby = client.get(
        "/api/v1/geo/incidents/nearby",
        params={"latitude": 13.08, "longitude": 80.27, "radius_km": 5},
    )
    bbox = client.get(
        "/api/v1/geo/incidents/bbox",
        params={"min_lat": 12, "min_lon": 79, "max_lat": 14, "max_lon": 81},
    )
    assert nearby.status_code == 403
    assert bbox.status_code == 403


# --- dispatch-only endpoints -------------------------------------------------
@pytest.mark.parametrize("role", NON_DISPATCH)
def test_priority_override_is_closed_to_non_dispatch_roles(
    client: TestClient, make_user, authed_client, incident_payload, role: UserRole
) -> None:
    incident = make_incident(authed_client, make_user, incident_payload)
    caller = authed_client(make_user(role))
    response = caller.post(
        f"/api/v1/incidents/{incident['id']}/priority",
        json={"override_band": "LOW", "reason": "Trying to downgrade this."},
    )
    assert response.status_code in (403, 404)


@pytest.mark.parametrize("role", NON_DISPATCH)
def test_fact_correction_is_closed_to_non_dispatch_roles(
    client: TestClient, make_user, authed_client, incident_payload, role: UserRole
) -> None:
    incident = make_incident(authed_client, make_user, incident_payload)
    caller = authed_client(make_user(role))
    response = caller.patch(
        f"/api/v1/incidents/{incident['id']}", json={"people_affected": 99}
    )
    assert response.status_code in (403, 404)


@pytest.mark.parametrize("role", NON_DISPATCH)
def test_assignment_is_closed_to_non_dispatch_roles(
    client: TestClient, make_user, authed_client, incident_payload, role: UserRole
) -> None:
    incident = make_incident(authed_client, make_user, incident_payload)
    caller = authed_client(make_user(role))
    response = caller.post(
        f"/api/v1/incidents/{incident['id']}/assign", json={"assigned_to_id": None}
    )
    assert response.status_code in (403, 404)


# --- admin-only endpoints ----------------------------------------------------
@pytest.mark.parametrize("role", NON_ADMIN)
def test_user_administration_is_closed_to_non_admins(as_role, role: UserRole) -> None:
    client, _ = as_role(role)
    assert client.get("/api/v1/users").status_code == 403
    assert (
        client.post(
            "/api/v1/users",
            json={
                "email": "new.operator@example.org",
                "password": "a-long-enough-passphrase",
                "full_name": "New Operator",
                "role": "DISPATCHER",
            },
        ).status_code
        == 403
    )


def test_an_admin_can_create_an_operational_account(as_role) -> None:
    client, _ = as_role(UserRole.ADMIN)
    response = client.post(
        "/api/v1/users",
        json={
            "email": "new.dispatcher@example.org",
            "password": "a-long-enough-passphrase",
            "full_name": "New Dispatcher",
            "role": "DISPATCHER",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "DISPATCHER"


def test_an_admin_cannot_create_a_super_admin(as_role) -> None:
    client, _ = as_role(UserRole.ADMIN)
    response = client.post(
        "/api/v1/users",
        json={
            "email": "escalation@example.org",
            "password": "a-long-enough-passphrase",
            "full_name": "Escalation Attempt",
            "role": "SUPER_ADMIN",
        },
    )
    assert response.status_code == 403


def test_an_admin_cannot_change_their_own_role(
    client: TestClient, make_user, authed_client
) -> None:
    """Self-promotion, and locking an organisation out of its own console, are
    both prevented by the same rule."""
    admin = make_user(UserRole.ADMIN)
    caller = authed_client(admin)
    assert (
        caller.patch(
            f"/api/v1/users/{admin.id}", json={"role": "SUPER_ADMIN"}
        ).status_code
        == 403
    )
    assert (
        caller.patch(f"/api/v1/users/{admin.id}", json={"is_active": False}).status_code
        == 403
    )


def test_an_admin_cannot_modify_a_super_admin(
    client: TestClient, make_user, authed_client
) -> None:
    target = make_user(UserRole.SUPER_ADMIN)
    caller = authed_client(make_user(UserRole.ADMIN))
    assert (
        caller.patch(f"/api/v1/users/{target.id}", json={"is_active": False}).status_code
        == 403
    )


def test_a_user_cannot_promote_themselves_through_the_profile_endpoint(
    as_role,
) -> None:
    client, _user = as_role(UserRole.CITIZEN)
    response = client.patch("/api/v1/users/me", json={"role": "ADMIN"})
    # ``role`` is not part of the self-update schema, so it is simply ignored.
    assert response.status_code in (200, 400)
    assert client.get("/api/v1/users/me").json()["role"] == "CITIZEN"


# --- ownership ---------------------------------------------------------------
def test_one_citizen_cannot_read_another_citizens_incident(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    """The response is 404, not 403: the API does not confirm it exists."""
    incident = make_incident(authed_client, make_user, incident_payload)
    stranger = authed_client(make_user(UserRole.CITIZEN))

    response = stranger.get(f"/api/v1/incidents/{incident['id']}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_one_citizen_cannot_read_another_citizens_history(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    incident = make_incident(authed_client, make_user, incident_payload)
    stranger = authed_client(make_user(UserRole.CITIZEN))
    assert stranger.get(f"/api/v1/incidents/{incident['id']}/history").status_code == 404


def test_one_citizen_cannot_cancel_another_citizens_incident(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    incident = make_incident(authed_client, make_user, incident_payload)
    stranger = authed_client(make_user(UserRole.CITIZEN))
    response = stranger.post(
        f"/api/v1/incidents/{incident['id']}/status", json={"status": "CANCELLED"}
    )
    assert response.status_code == 404


def test_the_reporter_can_read_their_own_incident(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    reporter = make_user(UserRole.CITIZEN)
    created = (
        authed_client(reporter).post("/api/v1/incidents", json=incident_payload).json()
    )
    assert (
        authed_client(reporter).get(f"/api/v1/incidents/{created['id']}").status_code
        == 200
    )


def test_a_responder_may_read_but_not_dispatch(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    incident = make_incident(authed_client, make_user, incident_payload)
    responder = authed_client(make_user(UserRole.RESPONDER))

    assert responder.get(f"/api/v1/incidents/{incident['id']}").status_code == 200
    assert responder.get("/api/v1/incidents").status_code == 200
    assert (
        responder.post(
            f"/api/v1/incidents/{incident['id']}/status", json={"status": "RECEIVED"}
        ).status_code
        == 403
    )
