"""What a client sees when the database cannot be reached.

These need no database: the point is the opposite. The connection is a real one to a port
nothing listens on, so the driver raises the same ``OperationalError`` a stopped or
unreachable PostgreSQL would, rather than a mock that merely looks like it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app

#: Port 1 is never a database; the connection is refused at once, not after a timeout.
UNREACHABLE_URL = "postgresql+psycopg://nobody:not-a-real-password@127.0.0.1:1/none"

REGISTRATION = {
    "email": "synthetic.user@example.org",
    "password": "correct-horse-battery-staple",
    "full_name": "Synthetic User",
}


@pytest.fixture
def client_without_database() -> Iterator[TestClient]:
    engine = create_engine(UNREACHABLE_URL, connect_args={"connect_timeout": 2})
    factory = sessionmaker(bind=engine)

    def _unreachable() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = _unreachable
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    engine.dispose()


def test_registration_reports_the_service_unavailable_not_an_internal_error(
    client_without_database: TestClient,
) -> None:
    response = client_without_database.post("/api/v1/auth/register", json=REGISTRATION)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.headers["retry-after"] == "5"


def test_the_error_does_not_leak_driver_or_connection_detail(
    client_without_database: TestClient,
) -> None:
    body = client_without_database.post("/api/v1/auth/register", json=REGISTRATION).text

    for secret in ("127.0.0.1", "nobody", "not-a-real-password", "psycopg", "refused"):
        assert secret not in body


def test_the_error_carries_cors_headers_so_the_browser_can_read_it(
    client_without_database: TestClient,
) -> None:
    """Without them the browser hides the status and the visitor only sees
    "Failed to fetch" — indistinguishable from the server being unreachable."""
    origin = get_settings().cors_origins[0]
    response = client_without_database.post(
        "/api/v1/auth/register", json=REGISTRATION, headers={"Origin": origin}
    )

    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == origin


def test_the_health_endpoint_still_answers_when_the_database_is_down(
    client_without_database: TestClient,
) -> None:
    """Liveness must not depend on the database, or an orchestrator restarts a healthy
    process because its dependency is down."""
    assert client_without_database.get("/api/v1/health").status_code == 200
