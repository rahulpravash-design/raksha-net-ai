"""Hospital and inbound-notice persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value
from app.models.enums import HospitalNoticeStatus
from app.models.hospital import Hospital, InboundPatientNotice
from app.utils.geo import Coordinates, to_ewkt

CLOSED_NOTICE_STATUSES = (
    HospitalNoticeStatus.ARRIVED,
    HospitalNoticeStatus.DIVERTED,
    HospitalNoticeStatus.CANCELLED,
)


class HospitalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- hospitals ----------------------------------------------------------
    def add(self, hospital: Hospital) -> Hospital:
        self.session.add(hospital)
        self.session.flush()
        return hospital

    def set_location(self, hospital: Hospital, coords: Coordinates) -> None:
        hospital.latitude = coords.latitude
        hospital.longitude = coords.longitude
        hospital.geom = to_ewkt(coords)

    def get(self, hospital_id: uuid.UUID) -> Hospital | None:
        return self.session.get(Hospital, hospital_id)

    def get_by_code(self, code: str) -> Hospital | None:
        return self.session.scalars(select(Hospital).where(Hospital.code == code)).first()

    def list_all(
        self, *, offset: int, limit: int, active_only: bool = True
    ) -> tuple[list[Hospital], int]:
        stmt = select(Hospital)
        if active_only:
            stmt = stmt.where(Hospital.is_active.is_(True))
        total = int(
            self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = (
            self.session.scalars(stmt.order_by(Hospital.name).offset(offset).limit(limit))
            .unique()
            .all()
        )
        return list(rows), total

    def find_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        accepting_only: bool = True,
        needs_icu: bool = False,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Hospitals within range that can actually take a patient.

        "Has a free bed" is part of the filter, not a detail the caller has to
        notice afterwards — a full hospital is not a nearby hospital.
        """
        sql = text("""
            SELECT h.id,
                   h.code,
                   h.name,
                   h.latitude::float8  AS latitude,
                   h.longitude::float8 AS longitude,
                   h.available_beds,
                   h.icu_available,
                   h.accepting_emergencies,
                   h.specialties,
                   h.contact_phone,
                   ST_Distance(h.geom, ref.geom) / 1000.0 AS distance_km
            FROM hospitals h
            CROSS JOIN (
                SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geom
            ) ref
            WHERE ST_DWithin(h.geom, ref.geom, :radius_m)
              AND h.is_active = TRUE
              AND (:accepting_only = FALSE OR h.accepting_emergencies = TRUE)
              AND (:accepting_only = FALSE OR h.available_beds > 0)
              AND (:needs_icu = FALSE OR h.icu_available > 0)
            ORDER BY distance_km ASC
            LIMIT :limit
            """)
        rows = self.session.execute(
            sql,
            {
                "lat": latitude,
                "lon": longitude,
                "radius_m": radius_km * 1000.0,
                "accepting_only": accepting_only,
                "needs_icu": needs_icu,
                "limit": limit,
            },
        ).mappings()
        # Raw SQL bypasses ``EncryptedString``, so decrypt by hand here.
        return [
            {**row, "contact_phone": decrypt_value(row["contact_phone"])} for row in rows
        ]

    # -- notices ------------------------------------------------------------
    def add_notice(self, notice: InboundPatientNotice) -> InboundPatientNotice:
        self.session.add(notice)
        self.session.flush()
        return notice

    def get_notice(self, notice_id: uuid.UUID) -> InboundPatientNotice | None:
        return self.session.get(InboundPatientNotice, notice_id)

    def list_notices_for_hospital(
        self, hospital_id: uuid.UUID, *, open_only: bool = True
    ) -> list[InboundPatientNotice]:
        stmt = select(InboundPatientNotice).where(
            InboundPatientNotice.hospital_id == hospital_id
        )
        if open_only:
            stmt = stmt.where(
                InboundPatientNotice.status.notin_(list(CLOSED_NOTICE_STATUSES))
            )
        stmt = stmt.order_by(InboundPatientNotice.created_at.desc())
        return list(self.session.scalars(stmt).unique().all())

    def list_notices_for_incident(
        self, incident_id: uuid.UUID
    ) -> list[InboundPatientNotice]:
        stmt = (
            select(InboundPatientNotice)
            .where(InboundPatientNotice.incident_id == incident_id)
            .order_by(InboundPatientNotice.created_at.desc())
        )
        return list(self.session.scalars(stmt).unique().all())
