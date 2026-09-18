"""Incident persistence, including every spatial query.

All PostGIS usage is confined to this module. Services ask for "incidents
within N kilometres"; they never build SQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import (
    OPEN_STATUSES,
    IncidentCategory,
    IncidentStatus,
    PriorityBand,
)
from app.models.incident import Incident, IncidentMedia, IncidentStatusHistory
from app.utils.geo import Coordinates, to_ewkt

#: Hard ceiling on a viewport query, so a zoomed-out map cannot pull the table.
MAP_QUERY_HARD_LIMIT = 2000


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- writes -------------------------------------------------------------
    def add(self, incident: Incident) -> Incident:
        self.session.add(incident)
        self.session.flush()
        return incident

    def set_location(self, incident: Incident, coords: Coordinates) -> None:
        """Write both coordinate representations together.

        Keeping this in one place is what guarantees ``latitude``/``longitude``
        and ``geom`` cannot drift apart.
        """
        incident.latitude = coords.latitude
        incident.longitude = coords.longitude
        incident.geom = to_ewkt(coords)

    def add_status_history(
        self,
        *,
        incident_id: uuid.UUID,
        from_status: IncidentStatus | None,
        to_status: IncidentStatus,
        changed_by_id: uuid.UUID | None,
        note: str | None = None,
    ) -> IncidentStatusHistory:
        entry = IncidentStatusHistory(
            incident_id=incident_id,
            from_status=from_status,
            to_status=to_status,
            changed_by_id=changed_by_id,
            note=note,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def add_media(self, media: IncidentMedia) -> IncidentMedia:
        self.session.add(media)
        self.session.flush()
        return media

    # -- reads --------------------------------------------------------------
    def get(self, incident_id: uuid.UUID) -> Incident | None:
        return self.session.get(Incident, incident_id)

    def get_detailed(self, incident_id: uuid.UUID) -> Incident | None:
        stmt = (
            select(Incident)
            .where(Incident.id == incident_id)
            .options(
                joinedload(Incident.reported_by),
                joinedload(Incident.assigned_to),
                selectinload(Incident.media),
            )
        )
        return self.session.scalars(stmt).unique().first()

    def get_by_reference(self, reference_code: str) -> Incident | None:
        stmt = select(Incident).where(Incident.reference_code == reference_code)
        return self.session.scalars(stmt).first()

    def reference_exists(self, reference_code: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(Incident)
            .where(Incident.reference_code == reference_code)
        )
        return bool(self.session.scalar(stmt))

    def get_media(self, media_id: uuid.UUID) -> IncidentMedia | None:
        return self.session.get(IncidentMedia, media_id)

    def list_media(self, incident_id: uuid.UUID) -> list[IncidentMedia]:
        stmt = (
            select(IncidentMedia)
            .where(IncidentMedia.incident_id == incident_id)
            .order_by(IncidentMedia.created_at)
        )
        return list(self.session.scalars(stmt))

    def list_history(self, incident_id: uuid.UUID) -> list[IncidentStatusHistory]:
        stmt = (
            select(IncidentStatusHistory)
            .where(IncidentStatusHistory.incident_id == incident_id)
            .options(joinedload(IncidentStatusHistory.changed_by))
            .order_by(IncidentStatusHistory.created_at)
        )
        return list(self.session.scalars(stmt))

    def search(
        self,
        *,
        offset: int,
        limit: int,
        reported_by_id: uuid.UUID | None = None,
        assigned_to_id: uuid.UUID | None = None,
        statuses: Sequence[IncidentStatus] | None = None,
        categories: Sequence[IncidentCategory] | None = None,
        priority_band: PriorityBand | None = None,
        query: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        sort: str = "priority",
    ) -> tuple[list[Incident], int]:
        stmt: Select[tuple[Incident]] = select(Incident)

        if reported_by_id is not None:
            stmt = stmt.where(Incident.reported_by_id == reported_by_id)
        if assigned_to_id is not None:
            stmt = stmt.where(Incident.assigned_to_id == assigned_to_id)
        if statuses:
            stmt = stmt.where(Incident.status.in_(list(statuses)))
        if open_only:
            stmt = stmt.where(Incident.status.in_(list(OPEN_STATUSES)))
        if categories:
            stmt = stmt.where(Incident.category.in_(list(categories)))
        if priority_band is not None:
            stmt = stmt.where(Incident.priority_band == priority_band)
        if since is not None:
            stmt = stmt.where(Incident.created_at >= since)
        if until is not None:
            stmt = stmt.where(Incident.created_at <= until)
        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Incident.description.ilike(pattern),
                    Incident.reference_code.ilike(pattern),
                    Incident.address_text.ilike(pattern),
                    Incident.landmark.ilike(pattern),
                )
            )

        total = (
            self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )

        stmt = stmt.order_by(*self._order_by(sort)).offset(offset).limit(limit)
        rows = list(self.session.scalars(stmt).unique())
        return rows, total

    @staticmethod
    def _order_by(sort: str) -> tuple[Any, ...]:
        if sort == "created_at":
            return (Incident.created_at.asc(),)
        if sort == "-created_at":
            return (Incident.created_at.desc(),)
        # Default queue order: most urgent first, oldest first within a band.
        return (
            Incident.priority_score.desc().nullslast(),
            Incident.created_at.asc(),
        )

    # -- spatial ------------------------------------------------------------
    def find_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int = 50,
        open_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Incidents within ``radius_km``, nearest and most urgent first.

        ``ST_DWithin`` is used rather than a distance comparison because only
        the former can use the GIST index.
        """
        sql = text("""
            SELECT i.id,
                   i.reference_code,
                   i.category::text        AS category,
                   i.status::text          AS status,
                   i.priority_band::text   AS priority_band,
                   i.priority_score,
                   i.latitude::float8      AS latitude,
                   i.longitude::float8     AS longitude,
                   ST_Distance(i.geom, ref.geom) / 1000.0 AS distance_km
            FROM incidents i
            CROSS JOIN (
                SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geom
            ) ref
            WHERE ST_DWithin(i.geom, ref.geom, :radius_m)
              AND (:open_only = FALSE OR i.status = ANY(:open_statuses))
            ORDER BY i.priority_score DESC NULLS LAST, distance_km ASC
            LIMIT :limit
            """)
        rows = self.session.execute(
            sql,
            {
                "lat": latitude,
                "lon": longitude,
                "radius_m": radius_km * 1000.0,
                "open_only": open_only,
                "open_statuses": [status.value for status in OPEN_STATUSES],
                "limit": limit,
            },
        ).mappings()
        return [dict(row) for row in rows]

    def find_in_bbox(
        self,
        *,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        limit: int = 500,
        open_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Incidents inside a map viewport."""
        sql = text("""
            SELECT i.id,
                   i.reference_code,
                   i.category::text      AS category,
                   i.status::text        AS status,
                   i.priority_band::text AS priority_band,
                   i.priority_score,
                   i.people_affected,
                   i.people_trapped,
                   i.latitude::float8    AS latitude,
                   i.longitude::float8   AS longitude,
                   i.created_at
            FROM incidents i
            WHERE i.geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)::geography
              AND (:open_only = FALSE OR i.status = ANY(:open_statuses))
            ORDER BY i.priority_score DESC NULLS LAST, i.created_at DESC
            LIMIT :limit
            """)
        rows = self.session.execute(
            sql,
            {
                "min_lat": min_lat,
                "min_lon": min_lon,
                "max_lat": max_lat,
                "max_lon": max_lon,
                "open_only": open_only,
                "open_statuses": [status.value for status in OPEN_STATUSES],
                "limit": min(limit, MAP_QUERY_HARD_LIMIT),
            },
        ).mappings()
        return [dict(row) for row in rows]

    # -- aggregates ---------------------------------------------------------
    def count_by(self, column: Any, *, open_only: bool = True) -> dict[str, int]:
        stmt = select(column, func.count()).group_by(column)
        if open_only:
            stmt = stmt.where(Incident.status.in_(list(OPEN_STATUSES)))
        return {
            (key.value if hasattr(key, "value") else str(key)): count
            for key, count in self.session.execute(stmt).all()
            if key is not None
        }

    def count_open(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Incident)
            .where(Incident.status.in_(list(OPEN_STATUSES)))
        )
        return int(self.session.scalar(stmt) or 0)

    def count_unassigned_open(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.status.in_(list(OPEN_STATUSES)),
                Incident.assigned_to_id.is_(None),
            )
        )
        return int(self.session.scalar(stmt) or 0)
