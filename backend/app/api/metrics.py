"""The Prometheus scrape endpoint."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import AppSettings, DbSession
from app.core import metrics
from app.core.errors import NotAuthenticatedError, NotFoundError
from app.services.operational_metrics import refresh_gauges

router = APIRouter(tags=["operations"], include_in_schema=False)


def _presented_token(request: Request) -> str:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


@router.get("/metrics")
def scrape(request: Request, session: DbSession, settings: AppSettings) -> Response:
    """Metrics in Prometheus text format, for a scraper holding the token.

    With ``RAKSHA_METRICS_TOKEN`` unset the endpoint does not exist. It is
    authenticated before the database is touched, and a missing token and a
    wrong one are indistinguishable.
    """
    if settings.metrics_token is None:
        raise NotFoundError()

    expected = settings.metrics_token.get_secret_value().encode()
    if not hmac.compare_digest(_presented_token(request).encode(), expected):
        raise NotAuthenticatedError()

    refresh_gauges(session)
    return Response(
        content=generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST
    )
