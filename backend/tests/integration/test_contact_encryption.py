"""Contact details are ciphertext in the database and plaintext in the API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import UserRole

PHONE = "+919876543210"


def authenticate_as(client: TestClient, user) -> TestClient:
    token, _ = create_access_token(user.id, user.role.value)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


_QUERIES = {
    "incidents": "SELECT contact_phone FROM incidents WHERE contact_phone IS NOT NULL",
    "resources": "SELECT contact_phone FROM resources WHERE contact_phone IS NOT NULL",
    "hospitals": "SELECT contact_phone FROM hospitals WHERE contact_phone IS NOT NULL",
}


def _stored(db_session: Session, table: str) -> list[str]:
    return list(db_session.execute(text(_QUERIES[table])).scalars())


def test_an_incident_contact_number_is_encrypted_at_rest(
    client: TestClient, make_user, incident_payload, db_session: Session
) -> None:
    authenticate_as(client, make_user(UserRole.CITIZEN))
    created = client.post(
        "/api/v1/incidents", json=incident_payload | {"contact_phone": PHONE}
    )
    assert created.status_code == 201
    assert created.json()["contact_phone"] == PHONE

    stored = _stored(db_session, "incidents")
    assert len(stored) == 1
    assert PHONE not in stored[0]
    assert stored[0].startswith("gAAAA")


def test_a_resource_contact_number_is_encrypted_at_rest(
    client: TestClient, make_user, db_session: Session
) -> None:
    authenticate_as(client, make_user(UserRole.DISPATCHER))
    created = client.post(
        "/api/v1/resources",
        json={
            "call_sign": "AMB-ENC",
            "name": "Encrypted Ambulance",
            "resource_type": "AMBULANCE",
            "latitude": 13.0827,
            "longitude": 80.2707,
            "contact_phone": PHONE,
        },
    )
    assert created.status_code == 201
    assert created.json()["contact_phone"] == PHONE
    assert PHONE not in _stored(db_session, "resources")[0]


def test_a_hospital_contact_number_is_encrypted_at_rest_and_readable_by_search(
    client: TestClient, make_user, db_session: Session
) -> None:
    """The nearby search uses raw SQL, which bypasses the column type."""
    authenticate_as(client, make_user(UserRole.ADMIN))
    created = client.post(
        "/api/v1/hospitals",
        json={
            "code": "ENC-H1",
            "name": "Encrypted General",
            "latitude": 13.0827,
            "longitude": 80.2707,
            "total_beds": 10,
            "available_beds": 5,
            "contact_phone": PHONE,
        },
    )
    assert created.status_code == 201, created.text
    assert PHONE not in _stored(db_session, "hospitals")[0]

    nearby = client.get(
        "/api/v1/hospitals/nearby",
        params={"latitude": 13.0827, "longitude": 80.2707},
    )
    assert nearby.status_code == 200, nearby.text
    assert nearby.json()["items"][0]["contact_phone"] == PHONE
