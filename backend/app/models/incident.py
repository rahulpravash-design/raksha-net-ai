"""Incident, media, status history and audit entities."""

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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import EncryptedString
from app.models.enums import (
    IncidentCategory,
    IncidentStatus,
    MediaType,
    PriorityBand,
    SeverityLevel,
    UserRole,
)
from app.models.user import User


class Incident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reported emergency.

    Coordinates are stored twice on purpose: ``latitude``/``longitude`` are the
    durable, exportable values, and ``geom`` is the indexed value the spatial
    queries use. The repository writes both in one transaction so they cannot
    drift (``docs/GIS_ARCHITECTURE.md`` section 2).
    """

    __tablename__ = "incidents"

    reference_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[IncidentCategory] = mapped_column(
        Enum(IncidentCategory, name="incident_category", native_enum=True),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    location_accuracy_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address_text: Mapped[str | None] = mapped_column(String(400), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", native_enum=True),
        nullable=False,
        default=IncidentStatus.REPORTED,
        index=True,
    )
    severity: Mapped[SeverityLevel | None] = mapped_column(
        Enum(SeverityLevel, name="severity_level", native_enum=True), nullable=True
    )
    priority_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_band: Mapped[PriorityBand | None] = mapped_column(
        Enum(PriorityBand, name="priority_band", native_enum=True), nullable=True
    )
    priority_factors: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    priority_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    #: Which priority-engine configuration produced the score above. Phase 7
    #: requires every score to carry its configuration version so a historical
    #: decision stays reproducible after the weights are tuned.
    priority_engine_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    priority_override_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    people_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    people_trapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    medical_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    immediate_danger: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contact_phone: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)

    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    reported_by: Mapped[User | None] = relationship(
        back_populates="reported_incidents", foreign_keys=[reported_by_id]
    )
    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id])
    media: Mapped[list[IncidentMedia]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentMedia.created_at",
    )
    status_history: Mapped[list[IncidentStatusHistory]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentStatusHistory.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "people_affected IS NULL OR people_affected >= 0",
            name="people_affected_non_negative",
        ),
        CheckConstraint(
            "priority_score IS NULL OR (priority_score >= 0 AND priority_score <= 100)",
            name="priority_score_range",
        ),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="longitude_range"),
        CheckConstraint("id <> duplicate_of_id", name="duplicate_not_self"),
        Index("ix_incidents_geom", "geom", postgresql_using="gist"),
        # Serves the control-centre queue: open incidents, highest priority first.
        Index(
            "ix_incidents_status_priority",
            "status",
            "priority_score",
            "created_at",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Incident {self.reference_code} {self.category} {self.status}>"


class IncidentMedia(UUIDPrimaryKeyMixin, Base):
    """A file attached to an incident.

    ``storage_key`` is generated by the media service; the client-supplied
    filename is metadata only and is never used as a path component.
    """

    __tablename__ = "incident_media"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, name="media_type", native_enum=True),
        nullable=False,
        default=MediaType.IMAGE,
    )
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    incident: Mapped[Incident] = relationship(back_populates="media")

    __table_args__ = (CheckConstraint("size_bytes > 0", name="size_bytes_positive"),)


class IncidentStatusHistory(UUIDPrimaryKeyMixin, Base):
    """Append-only record of every status transition."""

    __tablename__ = "incident_status_history"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[IncidentStatus | None] = mapped_column(
        Enum(IncidentStatus, name="incident_status", native_enum=True, create_type=False),
        nullable=True,
    )
    to_status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", native_enum=True, create_type=False),
        nullable=False,
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    incident: Mapped[Incident] = relationship(back_populates="status_history")
    # Needed so the audit trail can name who made each change; without it the
    # actor silently renders as blank in every history view.
    changed_by: Mapped[User | None] = relationship(lazy="joined")


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail.

    No application code path updates or deletes a row in this table.
    ``event_metadata`` is filtered before it is written: it never carries
    tokens, password material or precise coordinates.
    """

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_role: Mapped[UserRole | None] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True, create_type=False),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
