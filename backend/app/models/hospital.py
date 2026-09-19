"""Hospitals and the inbound-patient notices sent to them.

Data minimisation is the design constraint here (``docs/ROADMAP.md``, Phase 12;
``CLAUDE.md`` section 5). A hospital is told what it needs to prepare a bed —
how many patients, how severe, what kind of emergency, how long until they
arrive. It is not told who reported the incident, and the notice carries no
free-text description that could smuggle that back in: the only prose on it is
what a dispatcher deliberately writes as clinical notes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    HospitalNoticeStatus,
    IncidentCategory,
    SeverityLevel,
)
from app.models.user import User


class Hospital(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A receiving facility and its current capacity."""

    __tablename__ = "hospitals"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    total_beds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_beds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    icu_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    icu_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: False when the emergency department is on divert. A dispatcher can still
    #: send a notice — the receiving end may accept anyway — but the UI warns.
    accepting_emergencies: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    specialties: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    #: The hospital operator account that maintains this record's capacity.
    managed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    capacity_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    managed_by: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="longitude_range"),
        CheckConstraint(
            "available_beds >= 0 AND available_beds <= total_beds",
            name="available_beds_within_total",
        ),
        CheckConstraint(
            "icu_available >= 0 AND icu_available <= icu_total",
            name="icu_available_within_total",
        ),
        Index("ix_hospitals_geom", "geom", postgresql_using="gist"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Hospital {self.code} {self.available_beds}/{self.total_beds}>"


class InboundPatientNotice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """ "We are bringing you N patients, this severe, in this long."

    Note the columns that are *not* here: no reporter id, no reporter phone, no
    incident description, no coordinates. The incident is referenced by id for
    the audit trail, but nothing about the person who called it in travels with
    the notice.
    """

    __tablename__ = "inbound_patient_notices"

    hospital_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dispatch_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dispatches.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    status: Mapped[HospitalNoticeStatus] = mapped_column(
        Enum(HospitalNoticeStatus, name="hospital_notice_status", native_enum=True),
        nullable=False,
        default=HospitalNoticeStatus.NOTIFIED,
        index=True,
    )

    patient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    category: Mapped[IncidentCategory] = mapped_column(
        Enum(
            IncidentCategory,
            name="incident_category",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    severity: Mapped[SeverityLevel | None] = mapped_column(
        Enum(SeverityLevel, name="severity_level", native_enum=True, create_type=False),
        nullable=True,
    )
    eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Clinical notes a dispatcher chose to send. Not the citizen's report.
    clinical_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    response_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    hospital: Mapped[Hospital] = relationship(lazy="joined")
    created_by: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("patient_count >= 1", name="patient_count_positive"),
        CheckConstraint(
            "eta_minutes IS NULL OR eta_minutes >= 0", name="eta_non_negative"
        ),
        Index("ix_notices_hospital_status", "hospital_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<InboundPatientNotice {self.id} {self.status}>"
