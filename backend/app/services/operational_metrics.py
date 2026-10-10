"""Gauges that are read from live state at scrape time (Phase 18).

Counters and histograms are updated as requests happen; these values are only
meaningful at the moment someone asks, so they are set just before the scrape
is rendered.
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from app.core import metrics
from app.core.logging import get_logger
from app.db.session import get_engine
from app.repositories.incident_repository import IncidentRepository

logger = get_logger(__name__)


def refresh_gauges(session: Session) -> None:
    """Set the pool and queue gauges. Never raises: a scrape that fails exactly
    when the database is down would hide the very fault it exists to show."""
    pool = get_engine().pool
    if isinstance(pool, QueuePool):
        metrics.DB_POOL_SIZE.set(pool.size())
        metrics.DB_POOL_CHECKED_OUT.set(pool.checkedout())
        # overflow() is negative while the pool has not yet grown to its size.
        metrics.DB_POOL_OVERFLOW.set(max(pool.overflow(), 0))

    try:
        incidents = IncidentRepository(session)
        metrics.INCIDENTS_OPEN.set(incidents.count_open())
        metrics.INCIDENTS_UNASSIGNED.set(incidents.count_unassigned_open())
        metrics.DATABASE_UP.set(1)
    except SQLAlchemyError:
        session.rollback()
        metrics.DATABASE_UP.set(0)
        logger.warning("metrics_database_unavailable")
