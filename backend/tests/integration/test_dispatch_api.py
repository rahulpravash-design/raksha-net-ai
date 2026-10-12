"""Dispatch and the responder's view of it (Phase 11).

The rule under test throughout: a dispatch always carries the human who
approved it, and that human is the authenticated caller — never anything the
client can supply.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.incident import AuditLog

CHENNAI = (13.0827, 80.2707)


def make_resource(client: TestClient, **overrides: object) -> dict:
    payload = {
        "call_sign": "AMB-01",
        "name": "Kotturpuram Ambulance 1",
        "resource_type": "AMBULANCE",
        "latitude": CHENNAI[0],
        "longitude": CHENNAI[1],
        "capabilities": ["advanced_life_support"],
    }
    payload.update(overrides)
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def report(client: TestClient, payload: dict, **overrides: object) -> dict:
    response = client.post("/api/v1/incidents", json=payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def authenticate_as(client: TestClient, user) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def scene(as_role, incident_payload, make_user):
    """An incident, a unit, its responder, and an authenticated dispatcher."""
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    dispatcher_client, dispatcher = as_role(UserRole.DISPATCHER)
    responder = make_user(UserRole.RESPONDER)
    resource = make_resource(dispatcher_client, operator_id=str(responder.id))
    return {
        "client": dispatcher_client,
        "dispatcher": dispatcher,
        "responder": responder,
        "incident": incident,
        "resource": resource,
    }


def dispatch_unit(scene, **overrides: object) -> dict:
    payload = {"resource_id": scene["resource"]["id"]}
    payload.update(overrides)
    response = scene["client"].post(
        f"/api/v1/incidents/{scene['incident']['id']}/dispatches", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- approval ----------------------------------------------------------------
def test_a_dispatch_records_the_human_who_approved_it(scene) -> None:
    body = dispatch_unit(scene, note="Nearest unit, crew briefed.")

    assert body["approved_by"]["id"] == str(scene["dispatcher"].id)
    assert body["status"] == "DISPATCHED"
    assert body["estimated_minutes"] >= 1


def test_the_approver_cannot_be_supplied_by_the_client(scene) -> None:
    """A client-settable approver would make an unapproved dispatch look approved."""
    response = scene["client"].post(
        f"/api/v1/incidents/{scene['incident']['id']}/dispatches",
        json={
            "resource_id": scene["resource"]["id"],
            "approved_by_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 201
    assert response.json()["approved_by"]["id"] == str(scene["dispatcher"].id)


def test_the_database_refuses_a_dispatch_with_no_approver(
    scene, db_session: Session
) -> None:
    """Belt and braces: the NOT NULL constraint is the last line of defence."""
    dispatch = dispatch_unit(scene)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE dispatches SET approved_by_id = NULL WHERE id = :id"),
            {"id": dispatch["id"]},
        )
        db_session.flush()
    db_session.rollback()


def test_a_responder_cannot_dispatch(scene) -> None:
    client = authenticate_as(scene["client"], scene["responder"])
    response = client.post(
        f"/api/v1/incidents/{scene['incident']['id']}/dispatches",
        json={"resource_id": scene["resource"]["id"]},
    )
    assert response.status_code == 403


def test_a_citizen_cannot_dispatch(as_role, scene) -> None:
    citizen_client, _ = as_role(UserRole.CITIZEN)
    response = citizen_client.post(
        f"/api/v1/incidents/{scene['incident']['id']}/dispatches",
        json={"resource_id": scene["resource"]["id"]},
    )
    assert response.status_code == 403


def test_dispatching_is_audited(scene, db_session: Session) -> None:
    dispatch_unit(scene)
    entries = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "dispatch.created")
    ).all()
    assert len(entries) == 1


# --- availability ------------------------------------------------------------
def test_dispatching_marks_the_unit_unavailable(scene) -> None:
    dispatch_unit(scene)
    resource = scene["client"].get(f"/api/v1/resources/{scene['resource']['id']}").json()
    assert resource["status"] == "DISPATCHED"


def test_a_committed_unit_cannot_be_sent_to_a_second_incident(
    scene, as_role, incident_payload
) -> None:
    dispatch_unit(scene)

    citizen, _ = as_role(UserRole.CITIZEN)
    other = report(citizen, incident_payload)
    dispatcher = authenticate_as(scene["client"], scene["dispatcher"])

    response = dispatcher.post(
        f"/api/v1/incidents/{other['id']}/dispatches",
        json={"resource_id": scene["resource"]["id"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_ALREADY_DISPATCHED"


def test_completing_a_dispatch_frees_the_unit(scene) -> None:
    dispatch = dispatch_unit(scene)
    client = scene["client"]
    for step in ("ACKNOWLEDGED", "EN_ROUTE", "ON_SCENE", "COMPLETED"):
        response = client.post(
            f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": step}
        )
        assert response.status_code == 200, response.text

    resource = client.get(f"/api/v1/resources/{scene['resource']['id']}").json()
    assert resource["status"] == "AVAILABLE"


# --- the responder's view ----------------------------------------------------
def test_a_responder_sees_their_own_assignment(scene) -> None:
    dispatch_unit(scene)
    client = authenticate_as(scene["client"], scene["responder"])

    assignments = client.get("/api/v1/dispatches/mine").json()
    assert len(assignments) == 1
    assert assignments[0]["incident"]["reference_code"] == (
        scene["incident"]["reference_code"]
    )


def test_a_responder_sees_no_assignment_that_is_not_theirs(scene, as_role) -> None:
    dispatch_unit(scene)
    other_responder, _ = as_role(UserRole.RESPONDER)
    assert other_responder.get("/api/v1/dispatches/mine").json() == []


def test_the_scene_brief_omits_the_reporters_identity(scene) -> None:
    """A responder needs the scene, not the person who called it in."""
    dispatch_unit(scene)
    client = authenticate_as(scene["client"], scene["responder"])
    brief = client.get("/api/v1/dispatches/mine").json()[0]["incident"]

    assert not set(brief) & {"reported_by", "reported_by_id", "reporter"}
    assert brief["latitude"] and brief["description"]


def test_a_responder_can_report_progress(scene) -> None:
    dispatch = dispatch_unit(scene)
    client = authenticate_as(scene["client"], scene["responder"])

    response = client.post(
        f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": "EN_ROUTE"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "EN_ROUTE"
    assert response.json()["en_route_at"] is not None


def test_a_stranger_cannot_see_or_move_a_dispatch(scene, as_role) -> None:
    dispatch = dispatch_unit(scene)
    stranger, _ = as_role(UserRole.RESPONDER)

    assert stranger.get(f"/api/v1/dispatches/{dispatch['id']}").status_code == 404
    assert (
        stranger.post(
            f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": "EN_ROUTE"}
        ).status_code
        == 404
    )


# --- the dispatch lifecycle --------------------------------------------------
def test_an_illegal_transition_is_refused_with_the_legal_set(scene) -> None:
    dispatch = dispatch_unit(scene)
    response = scene["client"].post(
        f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": "COMPLETED"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DISPATCH_INVALID_TRANSITION"
    assert "EN_ROUTE" in response.json()["error"]["details"]["allowed"]


def test_cancelling_requires_a_reason(scene) -> None:
    dispatch = dispatch_unit(scene)
    response = scene["client"].post(
        f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": "CANCELLED"}
    )
    assert response.status_code == 400

    ok = scene["client"].post(
        f"/api/v1/dispatches/{dispatch['id']}/status",
        json={"status": "CANCELLED", "reason": "Stood down by the caller."},
    )
    assert ok.status_code == 200
    assert ok.json()["cancel_reason"] == "Stood down by the caller."


def test_a_finished_dispatch_cannot_be_moved_again(scene) -> None:
    dispatch = dispatch_unit(scene)
    scene["client"].post(
        f"/api/v1/dispatches/{dispatch['id']}/status",
        json={"status": "CANCELLED", "reason": "Duplicate call."},
    )
    response = scene["client"].post(
        f"/api/v1/dispatches/{dispatch['id']}/status", json={"status": "EN_ROUTE"}
    )
    assert response.status_code == 409


def test_a_closed_incident_cannot_receive_a_dispatch(scene) -> None:
    client = scene["client"]
    incident_id = scene["incident"]["id"]
    client.post(f"/api/v1/incidents/{incident_id}/status", json={"status": "REJECTED"})

    response = client.post(
        f"/api/v1/incidents/{incident_id}/dispatches",
        json={"resource_id": scene["resource"]["id"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INCIDENT_CLOSED"


def test_dispatching_an_unknown_resource_is_404(scene) -> None:
    response = scene["client"].post(
        f"/api/v1/incidents/{scene['incident']['id']}/dispatches",
        json={"resource_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_an_incident_lists_what_was_sent_to_it(scene) -> None:
    dispatch_unit(scene)
    rows = (
        scene["client"]
        .get(f"/api/v1/incidents/{scene['incident']['id']}/dispatches")
        .json()
    )
    assert len(rows) == 1
    assert rows[0]["resource"]["call_sign"] == "AMB-01"
