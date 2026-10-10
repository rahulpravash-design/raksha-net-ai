"""Liveness and readiness probes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import AppSettings, DbSession
from app.core.logging import get_logger
from app.schemas.common import HealthResponse, ReadinessResponse
from app.utils.schema_version import BEHIND, schema_state

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health(settings: AppSettings) -> HealthResponse:
    """Report that the process is running. No dependencies are touched."""
    return HealthResponse(
        status="ok", environment=settings.environment.value, version=settings.version
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"description": "A dependency is unavailable."}},
)
def readiness(
    session: DbSession, settings: AppSettings, response: Response
) -> ReadinessResponse:
    """Verify a database round trip, and that its schema is not behind the code.

    Returning 503 here lets the orchestrator pull the instance out of the load
    balancer instead of serving failures. A schema *behind* the code means the
    migration has not run yet, so the instance would fail on its first query that
    touches a missing column; holding traffic back is the safe answer. Optional
    dependencies (AI, Redis, the malware scanner) are deliberately not checked:
    the platform works without them, so they must not take it out of rotation.
    """
    started = time.perf_counter()
    database_status = "ok"
    postgis_version: str | None = None
    schema = "unknown"

    try:
        session.execute(text("SELECT 1"))
        postgis_version = session.scalar(text("SELECT postgis_lib_version()"))
        schema = schema_state(session)
    except Exception:
        logger.exception("readiness_check_failed")
        database_status = "unavailable"

    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    if database_status != "ok" or schema == BEHIND:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="degraded",
            database=database_status,
            schema_state=schema if database_status == "ok" else None,
            checks={"database_latency_ms": latency_ms},
        )

    return ReadinessResponse(
        status="ok",
        database=database_status,
        postgis=postgis_version,
        schema_state=schema,
        checks={"database_latency_ms": latency_ms},
    )
