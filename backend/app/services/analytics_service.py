"""Analytics: response-time and resolution metrics, category and resource
breakdowns, and coarsened hotspot detection.

Phase 14 is read-only decision support, same spirit as the rest of this
platform (``CLAUDE.md`` section 1): nothing here dispatches, reassigns or
changes an incident. It only summarises what already happened.

Restricted to dispatch-capable roles rather than every operational role.
Analytics reveals operational patterns — and, even coarsened, an approximate
sense of where incidents cluster — that a hospital operator's or a single
responder's job does not need.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError
from app.models.enums import DISPATCH_ROLES, IncidentCategory
from app.models.user import User
from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import (
    CategoryBreakdown,
    CategoryBreakdownItem,
    HotspotCell,
    Hotspots,
    ResourceUtilization,
    ResourceUtilizationItem,
    TimeStats,
)

#: Hotspot coordinates are snapped to this grid before they leave the
#: service — about 1.1 km at the equator. Do not make this finer without
#: re-reading ``CLAUDE.md`` section 5.
HOTSPOT_GRID_DEGREES = 0.01
HOTSPOT_LIMIT_DEFAULT = 50
HOTSPOT_LIMIT_MAX = 200


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AnalyticsRepository(session)

    def response_time(
        self,
        actor: User,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        category: IncidentCategory | None = None,
    ) -> TimeStats:
        self._assert_role(actor)
        row = self.repo.response_time_stats(since=since, until=until, category=category)
        return TimeStats(**row)

    def resolution_time(
        self,
        actor: User,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        category: IncidentCategory | None = None,
    ) -> TimeStats:
        self._assert_role(actor)
        row = self.repo.resolution_time_stats(since=since, until=until, category=category)
        return TimeStats(**row)

    def category_breakdown(
        self,
        actor: User,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> CategoryBreakdown:
        self._assert_role(actor)
        rows = self.repo.category_breakdown(since=since, until=until)
        items = [CategoryBreakdownItem(**row) for row in rows]
        return CategoryBreakdown(items=items, total=sum(item.count for item in items))

    def resource_utilization(
        self,
        actor: User,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> ResourceUtilization:
        self._assert_role(actor)
        rows = self.repo.resource_utilization(since=since, until=until)
        items = [
            ResourceUtilizationItem(
                resource_type=row["resource_type"],
                total_resources=row["total_resources"],
                available_now=row["available_now"],
                dispatches_in_period=row["dispatches_in_period"],
                avg_dispatches_per_resource=(
                    row["dispatches_in_period"] / row["total_resources"]
                    if row["total_resources"]
                    else 0.0
                ),
            )
            for row in rows
        ]
        return ResourceUtilization(items=items, period_start=since, period_end=until)

    def hotspots(
        self,
        actor: User,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        category: IncidentCategory | None = None,
        limit: int = HOTSPOT_LIMIT_DEFAULT,
    ) -> Hotspots:
        """Where incidents cluster, coarsened to a grid.

        The one rule that must not break here (``CLAUDE.md`` section 5): this
        never returns a raw incident coordinate, only a rounded cell centre
        and how many incidents fell inside it.
        """
        self._assert_role(actor)
        capped = min(limit, HOTSPOT_LIMIT_MAX)
        rows = self.repo.hotspots(
            since=since,
            until=until,
            category=category,
            cell_size_degrees=HOTSPOT_GRID_DEGREES,
            limit=capped,
        )
        items = [HotspotCell(**row) for row in rows]
        return Hotspots(cell_size_degrees=HOTSPOT_GRID_DEGREES, items=items)

    @staticmethod
    def _assert_role(actor: User) -> None:
        if actor.role not in DISPATCH_ROLES:
            raise ForbiddenError(
                "Only dispatchers and administrators can view analytics."
            )
