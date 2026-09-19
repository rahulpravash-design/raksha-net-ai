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
