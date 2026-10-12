"""Response resources: the units a dispatcher can send to an incident.

Location is stored the same way an incident's is — durable decimals plus an
indexed ``geography`` column kept in sync by the repository — so "nearest
available ambulance" is one indexed spatial query rather than a table scan
(``docs/GIS_ARCHITECTURE.md`` section 2).
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
from app.db.types import EncryptedString
from app.models.enums import ResourceStatus, ResourceType
from app.models.user import User


class Resource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One deployable unit: an ambulance, fire engine, rescue team, shelter.

    A resource's ``status`` is operational truth maintained by humans. Nothing
    in this system moves a resource on its own.
    """

    __tablename__ = "resources"

    call_sign: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, name="resource_type", native_enum=True),
        nullable=False,
        index=True,
    )
    status: Mapped[ResourceStatus] = mapped_column(
        Enum(ResourceStatus, name="resource_status", native_enum=True),
        nullable=False,
        default=ResourceStatus.AVAILABLE,
        index=True,
    )

    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    base_address: Mapped[str | None] = mapped_column(String(400), nullable=True)

    #: Free-form capability tags ("water_rescue", "advanced_life_support") used
    #: to narrow a recommendation. Advisory only: a dispatcher may send any
    #: unit they judge right.
    capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    crew_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)

    #: The responder account that operates this unit, if any. This is how the
    #: responder application finds the assignments that belong to its user.
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    operator: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="longitude_range"),
        CheckConstraint("crew_size IS NULL OR crew_size >= 0", name="crew_size_positive"),
        Index("ix_resources_geom", "geom", postgresql_using="gist"),
        Index("ix_resources_type_status", "resource_type", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Resource {self.call_sign} {self.resource_type} {self.status}>"
