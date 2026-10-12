"""Resource inventory, nearest-unit search and recommendations (Phase 10).

The property under test throughout: this API can *suggest* a unit, and it can
record where a unit is, but nothing here sends one anywhere.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.enums import UserRole

CHENNAI = (13.0827, 80.2707)


def make_resource(client: TestClient, **overrides: object) -> dict:
    payload = {
        "call_sign": "AMB-01",
        "name": "Kotturpuram Ambulance 1",
        "resource_type": "AMBULANCE",
        "latitude": CHENNAI[0],
        "longitude": CHENNAI[1],
        "capabilities": ["advanced_life_support"],
        "crew_size": 3,
    }
    payload.update(overrides)
    response = client.post("/api/v1/resources", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def report(client: TestClient, payload: dict, **overrides: object) -> dict:
    response = client.post("/api/v1/incidents", json=payload | overrides)
    assert response.status_code == 201, response.text
    return response.json()


# --- inventory ---------------------------------------------------------------
def test_a_dispatcher_can_register_a_resource(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    body = make_resource(client)

    assert body["call_sign"] == "AMB-01"
    assert body["status"] == "AVAILABLE"
    assert body["capabilities"] == ["advanced_life_support"]


def test_a_citizen_cannot_register_a_resource(as_role) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = client.post(
        "/api/v1/resources",
        json={
            "call_sign": "X-1",
            "name": "Unauthorised",
            "resource_type": "AMBULANCE",
            "latitude": CHENNAI[0],
            "longitude": CHENNAI[1],
        },
    )
    assert response.status_code == 403


def test_a_citizen_cannot_list_resources(as_role) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    assert client.get("/api/v1/resources").status_code == 403


def test_listing_resources_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/resources").status_code == 401


def test_a_duplicate_call_sign_is_a_conflict(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    make_resource(client)
    response = client.post(
        "/api/v1/resources",
        json={
            "call_sign": "AMB-01",
            "name": "Another unit",
            "resource_type": "AMBULANCE",
            "latitude": CHENNAI[0],
            "longitude": CHENNAI[1],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_CALL_SIGN_TAKEN"


def test_coordinates_outside_the_operating_area_are_refused(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    response = client.post(
        "/api/v1/resources",
        json={
            "call_sign": "FAR-1",
            "name": "Somewhere else entirely",
            "resource_type": "AMBULANCE",
            "latitude": 51.5,
            "longitude": -0.12,
        },
    )
    assert response.status_code == 400


# --- status ------------------------------------------------------------------
def test_a_responder_can_set_the_status_of_their_own_unit(as_role, make_user) -> None:
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    responder = make_user(UserRole.RESPONDER)
    resource = make_resource(dispatcher, operator_id=str(responder.id))

    from app.core.security import create_access_token

    token, _ = create_access_token(responder.id, responder.role.value)
    dispatcher.headers["Authorization"] = f"Bearer {token}"

    response = dispatcher.post(
        f"/api/v1/resources/{resource['id']}/status",
        json={"status": "EN_ROUTE", "latitude": 13.09, "longitude": 80.28},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "EN_ROUTE"


def test_a_responder_cannot_set_the_status_of_someone_elses_unit(
    as_role, make_user
) -> None:
    """A stranger's unit reads as absent, not as forbidden."""
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    resource = make_resource(dispatcher)

    responder, _ = as_role(UserRole.RESPONDER)
    response = responder.post(
        f"/api/v1/resources/{resource['id']}/status", json={"status": "EN_ROUTE"}
    )
    assert response.status_code == 404


def test_a_half_supplied_position_is_refused(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    resource = make_resource(client)
    response = client.post(
        f"/api/v1/resources/{resource['id']}/status",
        json={"status": "EN_ROUTE", "latitude": 13.09},
    )
    assert response.status_code == 400


# --- nearest unit ------------------------------------------------------------
def test_nearby_returns_units_in_distance_order(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    make_resource(client, call_sign="NEAR-1", latitude=13.0830, longitude=80.2710)
    make_resource(client, call_sign="FAR-1", latitude=13.1500, longitude=80.3500)

    body = client.get(
        "/api/v1/resources/nearby",
        params={"latitude": CHENNAI[0], "longitude": CHENNAI[1], "radius_km": 50},
    ).json()

    assert [item["call_sign"] for item in body["items"]] == ["NEAR-1", "FAR-1"]
    assert body["items"][0]["distance_km"] < body["items"][1]["distance_km"]


def test_nearby_excludes_units_outside_the_radius(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    make_resource(client, call_sign="NEAR-1", latitude=13.0830, longitude=80.2710)
    make_resource(client, call_sign="FAR-1", latitude=13.5000, longitude=80.5000)

    body = client.get(
        "/api/v1/resources/nearby",
        params={"latitude": CHENNAI[0], "longitude": CHENNAI[1], "radius_km": 2},
    ).json()
    assert [item["call_sign"] for item in body["items"]] == ["NEAR-1"]


def test_nearby_excludes_a_unit_that_is_not_available(as_role) -> None:
    client, _ = as_role(UserRole.DISPATCHER)
    busy = make_resource(client, call_sign="BUSY-1")
    client.post(f"/api/v1/resources/{busy['id']}/status", json={"status": "ON_SCENE"})

    body = client.get(
        "/api/v1/resources/nearby",
        params={"latitude": CHENNAI[0], "longitude": CHENNAI[1], "radius_km": 20},
    ).json()
    assert body["count"] == 0


# --- recommendations ---------------------------------------------------------
def test_recommendations_prefer_a_suitable_unit_over_a_merely_close_one(
    as_role, incident_payload
) -> None:
    """A closer unit that cannot do the job is not the better suggestion."""
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    # A flood report: a boat is the usual unit, an ambulance is not.
    make_resource(
        dispatcher,
        call_sign="AMB-CLOSE",
        resource_type="AMBULANCE",
        latitude=13.0828,
        longitude=80.2708,
    )
    make_resource(
        dispatcher,
        call_sign="BOAT-FAR",
        resource_type="RESCUE_BOAT",
        latitude=13.0900,
        longitude=80.2800,
        capabilities=["water_rescue"],
    )

    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    dispatcher, _ = as_role(UserRole.DISPATCHER)
    body = dispatcher.get(
        f"/api/v1/incidents/{incident['id']}/resource-recommendations"
    ).json()

    assert body["items"][0]["resource"]["call_sign"] == "BOAT-FAR"
    assert body["items"][0]["rank"] == 1
    assert body["items"][0]["type_match"] is True
    assert "water_rescue" in body["items"][0]["matched_capabilities"]


def test_every_recommendation_explains_itself(as_role, incident_payload) -> None:
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    make_resource(dispatcher, call_sign="BOAT-1", resource_type="RESCUE_BOAT")

    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    dispatcher, _ = as_role(UserRole.DISPATCHER)
    body = dispatcher.get(
        f"/api/v1/incidents/{incident['id']}/resource-recommendations"
    ).json()

    first = body["items"][0]
    assert first["reasons"], "a ranking a dispatcher cannot audit is not a suggestion"
    assert first["estimated_minutes"] >= 1


def test_recommendations_explain_an_empty_result(as_role, incident_payload) -> None:
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    dispatcher, _ = as_role(UserRole.DISPATCHER)
    body = dispatcher.get(
        f"/api/v1/incidents/{incident['id']}/resource-recommendations"
    ).json()

    assert body["items"] == []
    assert "No available resource" in body["note"]


def test_recommendations_for_an_unknown_incident_are_404(as_role) -> None:
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    response = dispatcher.get(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000"
        "/resource-recommendations"
    )
    assert response.status_code == 404


def test_a_citizen_cannot_read_recommendations(as_role, incident_payload) -> None:
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)
    response = citizen.get(f"/api/v1/incidents/{incident['id']}/resource-recommendations")
    assert response.status_code == 403


def test_the_recommendation_response_carries_no_dispatch_field(
    as_role, incident_payload
) -> None:
    """Phase 10 recommends. Committing a unit is Phase 11, and needs a human."""
    dispatcher, _ = as_role(UserRole.DISPATCHER)
    make_resource(dispatcher, call_sign="BOAT-2", resource_type="RESCUE_BOAT")
    citizen, _ = as_role(UserRole.CITIZEN)
    incident = report(citizen, incident_payload)

    dispatcher, _ = as_role(UserRole.DISPATCHER)
    body = dispatcher.get(
        f"/api/v1/incidents/{incident['id']}/resource-recommendations"
    ).json()

    assert not set(body) & {"dispatched", "assigned", "sent"}
    assert not set(body["items"][0]) & {"dispatched", "auto_assigned"}
