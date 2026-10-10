"""Incident reporting and lifecycle endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.enums import IncidentStatus, UserRole
from app.models.incident import AuditLog, Incident


def report(client: TestClient, payload: dict, **overrides: object) -> dict:
    response = client.post("/api/v1/incidents", json=payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


# --- creation ----------------------------------------------------------------
def test_a_citizen_can_report_an_emergency(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    body = report(client, incident_payload)

    assert body["status"] == IncidentStatus.REPORTED.value
    assert body["reference_code"].startswith("RKS-")
    assert body["priority_band"] == "CRITICAL"
    assert body["priority_score"] > 0
    assert body["priority_factors"], "the score must arrive with its explanation"


def test_the_reference_code_avoids_confusable_characters(
    as_role, incident_payload
) -> None:
    """The code is read aloud over the phone, so I/O/S/Z and 0/1/5/2 are excluded."""
    client, _ = as_role(UserRole.CITIZEN)
    code = report(client, incident_payload)["reference_code"].removeprefix("RKS-")
    assert not set(code) & set("IOSZ0125")


def test_reporting_requires_authentication(client: TestClient, incident_payload) -> None:
    assert client.post("/api/v1/incidents", json=incident_payload).status_code == 401


def test_an_initial_history_entry_is_written(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    incident = report(client, incident_payload)

    history = client.get(f"/api/v1/incidents/{incident['id']}/history").json()
    assert len(history) == 1
    assert history[0]["from_status"] is None
    assert history[0]["to_status"] == IncidentStatus.REPORTED.value


def test_creation_is_audited(as_role, incident_payload, db_session: Session) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    report(client, incident_payload)
    entries = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "incident.created")
    ).all()
    assert len(entries) == 1


def test_the_geometry_column_is_populated(
    as_role, incident_payload, db_session: Session
) -> None:
    """The indexed geometry and the stored decimals must agree."""
    client, _ = as_role(UserRole.CITIZEN)
    created = report(client, incident_payload)

    incident = db_session.scalars(
        select(Incident).where(Incident.id == created["id"])
    ).one()
    # ST_X/ST_Y are geometry functions, so the geography column is cast first.
    row = db_session.execute(
        text(
            "SELECT ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon "
            "FROM incidents WHERE id = :id"
        ),
        {"id": incident.id},
    ).one()
    assert round(row.lat, 4) == round(float(incident.latitude), 4)
    assert round(row.lon, 4) == round(float(incident.longitude), 4)


# --- validation --------------------------------------------------------------
def test_a_short_description_is_rejected(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = client.post(
        "/api/v1/incidents", json=incident_payload | {"description": "help"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_coordinates_outside_the_operating_area_are_rejected(
    as_role, incident_payload
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = client.post(
        "/api/v1/incidents",
        json=incident_payload | {"latitude": 51.5, "longitude": -0.12},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_COORDINATES"


def test_null_island_is_rejected(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = client.post(
        "/api/v1/incidents", json=incident_payload | {"latitude": 0, "longitude": 0}
    )
    assert response.status_code == 400


def test_an_out_of_range_latitude_is_rejected(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = client.post("/api/v1/incidents", json=incident_payload | {"latitude": 120})
    assert response.status_code == 400


def test_an_unknown_category_is_rejected(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = client.post(
        "/api/v1/incidents", json=incident_payload | {"category": "ALIENS"}
    )
    assert response.status_code == 400


def test_trapped_people_cannot_be_zero_affected(as_role, incident_payload) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = client.post(
        "/api/v1/incidents",
        json=incident_payload | {"people_trapped": True, "people_affected": 0},
    )
    assert response.status_code == 400


# --- reading -----------------------------------------------------------------
def test_a_citizen_sees_only_their_own_reports(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    reporter = make_user(UserRole.CITIZEN)
    report(authed_client(reporter), incident_payload)

    stranger = make_user(UserRole.CITIZEN)
    listing = authed_client(stranger).get("/api/v1/incidents/mine").json()
    assert listing["total"] == 0


def test_a_dispatcher_sees_the_whole_queue(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    queue = authed_client(make_user(UserRole.DISPATCHER)).get("/api/v1/incidents").json()
    assert queue["total"] == 1


def test_the_queue_is_ordered_by_priority(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    citizen = authed_client(make_user(UserRole.CITIZEN))
    report(
        citizen,
        incident_payload,
        category="OTHER",
        people_trapped=False,
        medical_required=False,
        immediate_danger=False,
        people_affected=1,
    )
    report(citizen, incident_payload)  # the critical one

    queue = authed_client(make_user(UserRole.DISPATCHER)).get("/api/v1/incidents").json()
    scores = [item["priority_score"] for item in queue["items"]]
    assert scores == sorted(scores, reverse=True)


def test_the_queue_can_be_filtered_by_category(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    citizen = authed_client(make_user(UserRole.CITIZEN))
    report(citizen, incident_payload, category="FLOOD")
    report(citizen, incident_payload, category="FIRE")

    dispatcher = authed_client(make_user(UserRole.DISPATCHER))
    filtered = dispatcher.get("/api/v1/incidents", params={"category": "FIRE"}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["category"] == "FIRE"


def test_the_queue_supports_free_text_search(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    citizen = authed_client(make_user(UserRole.CITIZEN))
    created = report(citizen, incident_payload)

    dispatcher = authed_client(make_user(UserRole.DISPATCHER))
    found = dispatcher.get(
        "/api/v1/incidents", params={"q": created["reference_code"]}
    ).json()
    assert found["total"] == 1


def test_stats_summarise_the_queue(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    stats = (
        authed_client(make_user(UserRole.DISPATCHER))
        .get("/api/v1/incidents/stats/summary")
        .json()
    )
    assert stats["total_open"] == 1
    assert stats["by_band"]["CRITICAL"] == 1
    assert stats["unassigned_open"] == 1


def test_an_unknown_incident_returns_not_found(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    response = client.get("/api/v1/incidents/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# --- lifecycle ---------------------------------------------------------------
def test_a_dispatcher_can_walk_the_happy_path(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    for target in (
        "RECEIVED",
        "UNDER_REVIEW",
        "PRIORITIZED",
        "ASSIGNED",
        "RESPONDER_EN_ROUTE",
        "ON_SCENE",
        "RESOLVED",
        "CLOSED",
    ):
        response = dispatcher.post(
            f"/api/v1/incidents/{created['id']}/status", json={"status": target}
        )
        assert response.status_code == 200, f"{target}: {response.text}"
        assert response.json()["status"] == target

    detail = dispatcher.get(f"/api/v1/incidents/{created['id']}").json()
    assert detail["resolved_at"] and detail["closed_at"]

    history = dispatcher.get(f"/api/v1/incidents/{created['id']}/history").json()
    assert len(history) == 9  # the initial entry plus eight transitions


def test_an_illegal_transition_is_refused(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    response = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/status", json={"status": "CLOSED"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INCIDENT_INVALID_TRANSITION"
    assert "RECEIVED" in response.json()["error"]["details"]["allowed"]


def test_the_reporter_can_cancel_before_assignment(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    reporter = make_user(UserRole.CITIZEN)
    created = report(authed_client(reporter), incident_payload)

    response = authed_client(reporter).post(
        f"/api/v1/incidents/{created['id']}/status",
        json={"status": "CANCELLED", "note": "False alarm, everyone is safe."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_the_reporter_cannot_cancel_once_a_crew_is_moving(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    reporter = make_user(UserRole.CITIZEN)
    created = report(authed_client(reporter), incident_payload)

    dispatcher = authed_client(make_user(UserRole.DISPATCHER))
    dispatcher.post(
        f"/api/v1/incidents/{created['id']}/status", json={"status": "RECEIVED"}
    )
    dispatcher.post(
        f"/api/v1/incidents/{created['id']}/status", json={"status": "UNDER_REVIEW"}
    )
    dispatcher.post(
        f"/api/v1/incidents/{created['id']}/status", json={"status": "ASSIGNED"}
    )

    response = authed_client(reporter).post(
        f"/api/v1/incidents/{created['id']}/status", json={"status": "CANCELLED"}
    )
    assert response.status_code == 403


def test_the_reporter_cannot_drive_the_lifecycle(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    reporter = make_user(UserRole.CITIZEN)
    created = report(authed_client(reporter), incident_payload)

    response = authed_client(reporter).post(
        f"/api/v1/incidents/{created['id']}/status", json={"status": "RESOLVED"}
    )
    assert response.status_code in (403, 409)


def test_marking_a_duplicate_requires_a_target(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    missing_target = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/status", json={"status": "DUPLICATE"}
    )
    assert missing_target.status_code == 400


def test_an_incident_cannot_duplicate_itself(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    response = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/status",
        json={"status": "DUPLICATE", "duplicate_of_id": created["id"]},
    )
    assert response.status_code == 400


# --- facts and priority ------------------------------------------------------
def test_correcting_the_facts_recomputes_the_priority(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(
        authed_client(make_user(UserRole.CITIZEN)),
        incident_payload,
        people_trapped=False,
        immediate_danger=False,
        medical_required=False,
        people_affected=1,
        category="OTHER",
    )
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    updated = dispatcher.patch(
        f"/api/v1/incidents/{created['id']}",
        json={"people_trapped": True, "immediate_danger": True, "people_affected": 6},
    ).json()
    assert updated["priority_score"] > created["priority_score"]


def test_an_override_needs_a_reason(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    response = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/priority", json={"override_band": "LOW"}
    )
    assert response.status_code == 400


def test_an_override_is_recorded_with_its_reason(
    client: TestClient, make_user, authed_client, incident_payload, db_session: Session
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    body = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/priority",
        json={
            "override_band": "LOW",
            "reason": "Reporter confirmed by phone it is resolved.",
        },
    ).json()

    assert body["priority_band"] == "LOW"
    assert body["priority_overridden"] is True
    assert "Reporter confirmed" in body["priority_override_reason"]

    audited = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "incident.priority_overridden")
    ).all()
    assert len(audited) == 1


def test_a_fact_correction_does_not_silently_discard_an_override(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    """An override is a human decision; only a human may withdraw it."""
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    dispatcher.post(
        f"/api/v1/incidents/{created['id']}/priority",
        json={"override_band": "LOW", "reason": "Verified as a minor incident."},
    )
    updated = dispatcher.patch(
        f"/api/v1/incidents/{created['id']}", json={"people_affected": 40}
    ).json()

    assert updated["priority_band"] == "LOW"
    assert updated["priority_overridden"] is True


def test_recomputing_clears_an_override(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    dispatcher.post(
        f"/api/v1/incidents/{created['id']}/priority",
        json={"override_band": "LOW", "reason": "Verified as a minor incident."},
    )
    recomputed = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/priority", json={}
    ).json()

    assert recomputed["priority_overridden"] is False
    assert recomputed["priority_band"] == "CRITICAL"


# --- assignment --------------------------------------------------------------
def test_an_incident_can_be_assigned_to_dispatch_staff(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    colleague = make_user(UserRole.DISPATCHER)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    body = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/assign",
        json={"assigned_to_id": str(colleague.id)},
    ).json()
    assert body["assigned_to"]["id"] == str(colleague.id)


@pytest.mark.parametrize("role", [UserRole.RESPONDER, UserRole.HOSPITAL_OPERATOR])
def test_an_incident_cannot_be_assigned_to_a_role_that_cannot_read_it(
    client: TestClient, make_user, authed_client, incident_payload, role: UserRole
) -> None:
    """Owning an incident you cannot open would be a contradiction. Field units
    are sent with a dispatch; they are not made the incident's assignee."""
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    response = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/assign",
        json={"assigned_to_id": str(make_user(role).id)},
    )
    assert response.status_code == 400


def test_a_citizen_cannot_be_assigned_an_incident(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    created = report(authed_client(make_user(UserRole.CITIZEN)), incident_payload)
    bystander = make_user(UserRole.CITIZEN)
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    response = dispatcher.post(
        f"/api/v1/incidents/{created['id']}/assign",
        json={"assigned_to_id": str(bystander.id)},
    )
    assert response.status_code == 400


def test_the_history_names_who_made_each_change(
    client: TestClient, make_user, authed_client, incident_payload
) -> None:
    """An audit trail that cannot say who acted is not an audit trail."""
    reporter = make_user(UserRole.CITIZEN, full_name="Asha Reporter")
    created = (
        authed_client(reporter).post("/api/v1/incidents", json=incident_payload).json()
    )

    operator = make_user(UserRole.DISPATCHER, full_name="Karthik Dispatcher")
    dispatcher = authed_client(operator)
    dispatcher.post(
        f"/api/v1/incidents/{created['id']}/status",
        json={"status": "RECEIVED", "note": "Acknowledged."},
    )

    history = dispatcher.get(f"/api/v1/incidents/{created['id']}/history").json()
    assert history[0]["changed_by"]["full_name"] == "Asha Reporter"
    assert history[1]["changed_by"]["full_name"] == "Karthik Dispatcher"
    assert history[1]["changed_by"]["role"] == "DISPATCHER"


# --- priority engine configuration (Phase 7) ---------------------------------
def test_the_engine_version_is_recorded_on_every_score(
    as_role, incident_payload, db_session: Session
) -> None:
    """A score without its configuration version cannot be reproduced later."""
    client, _ = as_role(UserRole.CITIZEN)
    created = report(client, incident_payload)

    incident = db_session.scalars(
        select(Incident).where(Incident.id == created["id"])
    ).one()
    assert incident.priority_engine_version == "1.0.0"


def test_priority_agreement_reports_overrides_against_the_engine(
    as_role, incident_payload
) -> None:
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    dispatcher, _ = as_role(UserRole.DISPATCHER)
    dispatcher.post(
        f"/api/v1/incidents/{incident['id']}/priority",
        json={"override_band": "LOW", "reason": "Reporter stood the callout down."},
    )

    summary = dispatcher.get("/api/v1/incidents/stats/priority-agreement").json()
    assert summary["overridden_count"] == 1
    assert summary["disagreement_count"] == 1  # engine said CRITICAL, human said LOW
    assert summary["override_rate"] > 0
    assert summary["cells"][0]["engine_band"] == "CRITICAL"
    assert summary["cells"][0]["override_band"] == "LOW"


def test_priority_agreement_is_not_public(client: TestClient) -> None:
    assert client.get("/api/v1/incidents/stats/priority-agreement").status_code == 401


def test_a_citizen_cannot_read_priority_agreement(as_role) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    assert client.get("/api/v1/incidents/stats/priority-agreement").status_code == 403
