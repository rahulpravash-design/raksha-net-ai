"""Dispatch: committing a resource to an incident.

``approved_by_id`` is ``NOT NULL`` by deliberate design
(``docs/ROADMAP.md``, Phase 11): there is no schema-legal way to record a
dispatch that no human approved. If some future code path ever tried to
dispatch automatically, the database would refuse the row rather than the
review catching it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DispatchStatus
from app.models.incident import Incident
from app.models.resource import Resource
from app.models.user import User


class Dispatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One resource sent to one incident, by one named human."""

    __tablename__ = "dispatches"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: The dispatcher who approved this. NOT NULL is the whole point.
    approved_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[DispatchStatus] = mapped_column(
        Enum(DispatchStatus, name="dispatch_status", native_enum=True),
        nullable=False,
        default=DispatchStatus.DISPATCHED,
        index=True,
    )

    #: Distance and ETA as they stood when the decision was made. Snapshotted
    #: rather than recomputed, so the record shows what the dispatcher saw.
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    en_route_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    on_scene_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    incident: Mapped[Incident] = relationship(lazy="joined")
    resource: Mapped[Resource] = relationship(lazy="joined")
    approved_by: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "distance_km IS NULL OR distance_km >= 0", name="distance_non_negative"
        ),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes >= 0",
            name="eta_non_negative",
        ),
        Index("ix_dispatches_incident_status", "incident_id", "status"),
        Index("ix_dispatches_resource_status", "resource_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Dispatch {self.id} {self.status}>"
