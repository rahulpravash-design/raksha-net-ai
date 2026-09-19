"""Analytics aggregation queries.

Everything here reads; nothing writes. ``CLAUDE.md`` section 5 requires
analytics to surface only aggregated or coarsened location, so ``hotspots``
is the only query here that touches a coordinate, and it never returns
anything finer than a grid cell — see ``app/services/analytics_service.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.enums import IncidentCategory


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def response_time_stats(
        self,
        *,
        since: datetime | None,
        until: datetime | None,
        category: IncidentCategory | None,
    ) -> dict[str, Any]:
        """Minutes from an incident's report to its first dispatch."""
        sql = text("""
            WITH first_dispatch AS (
                SELECT incident_id, MIN(created_at) AS dispatched_at
                FROM dispatches
                GROUP BY incident_id
            ),
            gaps AS (
                SELECT
                    EXTRACT(EPOCH FROM (fd.dispatched_at - i.created_at)) / 60.0 AS minutes
                FROM incidents i
                JOIN first_dispatch fd ON fd.incident_id = i.id
                WHERE (CAST(:since AS timestamptz) IS NULL OR i.created_at >= :since)
                  AND (CAST(:until AS timestamptz) IS NULL OR i.created_at <= :until)
                  AND (CAST(:category AS text) IS NULL OR i.category::text = :category)
            )
            SELECT
                COUNT(*)::int AS sample_size,
                AVG(minutes)::float8 AS avg_minutes,
                MIN(minutes)::float8 AS min_minutes,
                MAX(minutes)::float8 AS max_minutes,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY minutes)::float8 AS median_minutes
            FROM gaps
            """)
        row = (
            self.session.execute(
                sql,
                {
                    "since": since,
                    "until": until,
                    "category": category.value if category else None,
                },
            )
            .mappings()
            .one()
        )
        return dict(row)

    def resolution_time_stats(
        self,
        *,
        since: datetime | None,
        until: datetime | None,
        category: IncidentCategory | None,
    ) -> dict[str, Any]:
        """Minutes from an incident's report to its resolution.

        Only incidents with ``resolved_at`` set are counted — an incident
        still open has no resolution time yet, not a resolution time of zero.
        """
        sql = text("""
            WITH gaps AS (
                SELECT
                    EXTRACT(EPOCH FROM (i.resolved_at - i.created_at)) / 60.0 AS minutes
                FROM incidents i
                WHERE i.resolved_at IS NOT NULL
                  AND (CAST(:since AS timestamptz) IS NULL OR i.created_at >= :since)
                  AND (CAST(:until AS timestamptz) IS NULL OR i.created_at <= :until)
                  AND (CAST(:category AS text) IS NULL OR i.category::text = :category)
            )
            SELECT
                COUNT(*)::int AS sample_size,
                AVG(minutes)::float8 AS avg_minutes,
                MIN(minutes)::float8 AS min_minutes,
                MAX(minutes)::float8 AS max_minutes,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY minutes)::float8 AS median_minutes
            FROM gaps
            """)
        row = (
            self.session.execute(
                sql,
                {
                    "since": since,
                    "until": until,
                    "category": category.value if category else None,
                },
            )
            .mappings()
            .one()
        )
        return dict(row)

    def category_breakdown(
        self, *, since: datetime | None, until: datetime | None
    ) -> list[dict[str, Any]]:
        sql = text("""
            SELECT
                i.category::text AS category,
                COUNT(*)::int AS count,
                AVG(i.priority_score)::float8 AS avg_priority_score
            FROM incidents i
            WHERE (CAST(:since AS timestamptz) IS NULL OR i.created_at >= :since)
              AND (CAST(:until AS timestamptz) IS NULL OR i.created_at <= :until)
            GROUP BY i.category
            ORDER BY count DESC
            """)
        rows = self.session.execute(sql, {"since": since, "until": until}).mappings()
        return [dict(row) for row in rows]

    def resource_utilization(
        self, *, since: datetime | None, until: datetime | None
    ) -> list[dict[str, Any]]:
        sql = text("""
            SELECT
                r.resource_type::text AS resource_type,
                COUNT(DISTINCT r.id)::int AS total_resources,
                COUNT(DISTINCT r.id) FILTER (
                    WHERE r.status = 'AVAILABLE'
                )::int AS available_now,
                COUNT(d.id)::int AS dispatches_in_period
            FROM resources r
            LEFT JOIN dispatches d
                ON d.resource_id = r.id
               AND (CAST(:since AS timestamptz) IS NULL OR d.created_at >= :since)
               AND (CAST(:until AS timestamptz) IS NULL OR d.created_at <= :until)
            WHERE r.is_active = TRUE
            GROUP BY r.resource_type
            ORDER BY dispatches_in_period DESC
            """)
        rows = self.session.execute(sql, {"since": since, "until": until}).mappings()
        return [dict(row) for row in rows]

    def hotspots(
        self,
        *,
        since: datetime | None,
        until: datetime | None,
        category: IncidentCategory | None,
        cell_size_degrees: float,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Incident counts per grid cell.

        The coordinates returned are ``ROUND(value / cell_size) * cell_size``
        — the cell's centre, not any incident's actual position. Nothing
        upstream of this method may relax that rounding.
        """
        # The rounding happens entirely in ``numeric`` (exact decimal) space,
        # not ``float8``: two coordinates that round to the same grid cell
        # must produce the bit-identical value, or GROUP BY silently treats
        # them as different cells because of binary floating-point drift.
        # Grouped by the integer grid index, not the derived coordinate: the
        # index is a bare function of ``i.latitude``/``i.longitude`` with no
        # ambiguous alias, and wrapping the coordinate itself in MIN() below
        # sidesteps Postgres's functional-dependency check entirely — every
        # row in a group has the identical computed value, so MIN just
        # returns it.
        sql = text("""
            SELECT
                MIN((ROUND(i.latitude / CAST(:cell_size AS numeric))
                    * CAST(:cell_size AS numeric))::float8) AS latitude,
                MIN((ROUND(i.longitude / CAST(:cell_size AS numeric))
                    * CAST(:cell_size AS numeric))::float8) AS longitude,
                COUNT(*)::int AS incident_count
            FROM incidents i
            WHERE (CAST(:since AS timestamptz) IS NULL OR i.created_at >= :since)
              AND (CAST(:until AS timestamptz) IS NULL OR i.created_at <= :until)
              AND (CAST(:category AS text) IS NULL OR i.category::text = :category)
            GROUP BY
                ROUND(i.latitude / CAST(:cell_size AS numeric)),
                ROUND(i.longitude / CAST(:cell_size AS numeric))
            ORDER BY incident_count DESC
            LIMIT :limit
            """)
        rows = self.session.execute(
            sql,
            {
                "since": since,
                "until": until,
                "category": category.value if category else None,
                "cell_size": cell_size_degrees,
                "limit": limit,
            },
        ).mappings()
        return [dict(row) for row in rows]
