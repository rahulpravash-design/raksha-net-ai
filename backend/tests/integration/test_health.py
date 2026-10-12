"""Health and readiness probes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"


def test_readiness_confirms_the_database_and_postgis(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["postgis"], "PostGIS must be present — the spatial queries need it"
    assert body["checks"]["database_latency_ms"] >= 0


def test_every_response_carries_a_correlation_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["X-Request-ID"]


def test_a_supplied_correlation_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_security_headers_are_present(client: TestClient) -> None:
    headers = client.get("/api/v1/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    # An API that returns JSON has no legitimate use for script or style.
    assert headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    # Never asserted in the test environment: HSTS is meaningless over the
    # plain HTTP this suite talks, and is only sent in a production-like one.
    assert "Strict-Transport-Security" not in headers


def test_the_strict_csp_does_not_apply_to_the_interactive_docs(
    client: TestClient,
) -> None:
    """Swagger UI needs its own CDN script — the JSON API does not."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers


def test_root_points_at_the_health_endpoint(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["health"] == "/api/v1/health"


def test_an_unknown_path_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --- schema version in readiness (Phase 18) ----------------------------------
def _record_revision(db_session, revision: str) -> None:
    """Pretend migrations have run. Rolled back with the test transaction."""
    from sqlalchemy import text

    db_session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num varchar(32) NOT NULL)"
        )
    )
    db_session.execute(text("DELETE FROM alembic_version"))
    db_session.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:rev)"), {"rev": revision}
    )


def test_readiness_is_not_failed_by_a_database_with_no_recorded_revision(
    client: TestClient,
) -> None:
    """A create_all() or fully downgraded database has nothing to compare."""
    body = client.get("/api/v1/health/ready").json()
    assert body["status"] == "ok"
    assert body["schema_state"] == "unknown"


def test_a_schema_at_the_code_head_is_current(client: TestClient, db_session) -> None:
    from app.utils.schema_version import code_head

    head = code_head()
    assert head is not None, "the migrations directory must be discoverable"
    _record_revision(db_session, head)

    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["schema_state"] == "current"


def test_a_schema_behind_the_code_is_not_ready(client: TestClient, db_session) -> None:
    """Starting a new version before its migration has run must hold traffic back."""
    _record_revision(db_session, "0001_postgis")

    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["schema_state"] == "behind"


def test_a_schema_ahead_of_the_code_stays_ready_but_says_so(
    client: TestClient, db_session
) -> None:
    """After rolling the application back past a migration, the database is newer."""
    _record_revision(db_session, "9999_from_a_future_release")

    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["schema_state"] == "ahead"
