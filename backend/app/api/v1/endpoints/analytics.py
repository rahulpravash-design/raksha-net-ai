"""Analytics endpoints: read-only aggregates for dispatch-capable roles.

Nothing here changes an incident, a resource or a dispatch. See
``app/services/analytics_service.py`` for the coarsening rule that governs
the hotspot endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, DispatchUser
from app.models.enums import IncidentCategory
from app.schemas.analytics import (
    CategoryBreakdown,
    Hotspots,
    ResourceUtilization,
    TimeStats,
)
from app.services.analytics_service import HOTSPOT_LIMIT_MAX, AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/response-time", response_model=TimeStats, summary="Report-to-dispatch time")
def response_time(
    user: DispatchUser,
    session: DbSession,
    since: datetime | None = None,
    until: datetime | None = None,
    category: IncidentCategory | None = None,
) -> TimeStats:
    return AnalyticsService(session).response_time(
        user, since=since, until=until, category=category
    )


@router.get(
    "/resolution-time", response_model=TimeStats, summary="Report-to-resolved time"
)
def resolution_time(
    user: DispatchUser,
    session: DbSession,
    since: datetime | None = None,
    until: datetime | None = None,
    category: IncidentCategory | None = None,
) -> TimeStats:
    return AnalyticsService(session).resolution_time(
        user, since=since, until=until, category=category
    )


@router.get(
    "/category-breakdown",
    response_model=CategoryBreakdown,
    summary="Incident counts and average priority by category",
)
def category_breakdown(
    user: DispatchUser,
    session: DbSession,
    since: datetime | None = None,
    until: datetime | None = None,
) -> CategoryBreakdown:
    return AnalyticsService(session).category_breakdown(user, since=since, until=until)


@router.get(
    "/resource-utilization",
    response_model=ResourceUtilization,
    summary="Dispatches per resource type",
)
def resource_utilization(
    user: DispatchUser,
    session: DbSession,
    since: datetime | None = None,
    until: datetime | None = None,
) -> ResourceUtilization:
    return AnalyticsService(session).resource_utilization(user, since=since, until=until)


@router.get(
    "/hotspots",
    response_model=Hotspots,
    summary="Incident clusters on coarsened coordinates",
)
def hotspots(
    user: DispatchUser,
    session: DbSession,
    since: datetime | None = None,
    until: datetime | None = None,
    category: IncidentCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=HOTSPOT_LIMIT_MAX)] = 50,
) -> Hotspots:
    """Never a raw incident coordinate — see the service for the rule."""
    return AnalyticsService(session).hotspots(
        user, since=since, until=until, category=category, limit=limit
    )
