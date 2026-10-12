"""Resource persistence, including the nearest-unit spatial query.

All PostGIS for resources is confined here, exactly as it is for incidents:
services ask for "available ambulances within N km", they never build SQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.models.enums import ResourceStatus, ResourceType
from app.models.resource import Resource
from app.utils.geo import Coordinates, to_ewkt

#: Hard ceiling on any single nearest-unit query.
NEAREST_HARD_LIMIT = 100


class ResourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- writes -------------------------------------------------------------
    def add(self, resource: Resource) -> Resource:
        self.session.add(resource)
        self.session.flush()
        return resource

    def set_location(self, resource: Resource, coords: Coordinates) -> None:
        """Write both coordinate representations together, so they cannot drift."""
        resource.latitude = coords.latitude
        resource.longitude = coords.longitude
        resource.geom = to_ewkt(coords)

    # -- reads --------------------------------------------------------------
    def get(self, resource_id: uuid.UUID) -> Resource | None:
        return self.session.get(Resource, resource_id)

    def get_by_call_sign(self, call_sign: str) -> Resource | None:
        stmt = select(Resource).where(Resource.call_sign == call_sign)
        return self.session.scalars(stmt).first()

    def list_for_operator(self, operator_id: uuid.UUID) -> list[Resource]:
        stmt = select(Resource).where(Resource.operator_id == operator_id)
        return list(self.session.scalars(stmt).all())

    def search(
        self,
        *,
        offset: int,
        limit: int,
        resource_types: Sequence[ResourceType] | None = None,
        statuses: Sequence[ResourceStatus] | None = None,
        active_only: bool = True,
        query: str | None = None,
    ) -> tuple[list[Resource], int]:
        stmt: Select[tuple[Resource]] = select(Resource)
        if resource_types:
            stmt = stmt.where(Resource.resource_type.in_(list(resource_types)))
        if statuses:
            stmt = stmt.where(Resource.status.in_(list(statuses)))
        if active_only:
            stmt = stmt.where(Resource.is_active.is_(True))
        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                Resource.call_sign.ilike(pattern) | Resource.name.ilike(pattern)
            )

        total = int(
            self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = self.session.scalars(
            stmt.order_by(Resource.call_sign).offset(offset).limit(limit)
        ).all()
        return list(rows), total

    def count_by_status(self) -> dict[str, int]:
        stmt = (
            select(Resource.status, func.count())
            .where(Resource.is_active.is_(True))
            .group_by(Resource.status)
        )
        return {
            status.value: count
            for status, count in self.session.execute(stmt).all()
            if status is not None
        }

    def find_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        resource_types: Sequence[ResourceType] | None = None,
        available_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Resources within ``radius_km``, nearest first.

        ``ST_DWithin`` rather than a distance comparison, because only the
        former can use the GIST index.
        """
        sql = text("""
            SELECT r.id,
                   r.call_sign,
                   r.name,
                   r.resource_type::text AS resource_type,
                   r.status::text        AS status,
                   r.latitude::float8    AS latitude,
                   r.longitude::float8   AS longitude,
                   r.capabilities,
                   r.crew_size,
                   ST_Distance(r.geom, ref.geom) / 1000.0 AS distance_km
            FROM resources r
            CROSS JOIN (
                SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geom
            ) ref
            WHERE ST_DWithin(r.geom, ref.geom, :radius_m)
              AND r.is_active = TRUE
              AND (:all_types = TRUE OR r.resource_type::text = ANY(:types))
              AND (:available_only = FALSE OR r.status = 'AVAILABLE')
            ORDER BY distance_km ASC
            LIMIT :limit
            """)
        type_values = [item.value for item in (resource_types or [])]
        rows = self.session.execute(
            sql,
            {
                "lat": latitude,
                "lon": longitude,
                "radius_m": radius_km * 1000.0,
                "all_types": not type_values,
                "types": type_values,
                "available_only": available_only,
                "limit": min(limit, NEAREST_HARD_LIMIT),
            },
        ).mappings()
        return [dict(row) for row in rows]
