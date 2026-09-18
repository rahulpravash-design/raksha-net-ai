"""Incident request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    IncidentCategory,
    IncidentStatus,
    PriorityBand,
    SeverityLevel,
)
from app.schemas.common import ORMModel
from app.schemas.media import MediaRead
from app.schemas.user import UserSummary

DESCRIPTION_MIN = 10
DESCRIPTION_MAX = 4000

#: Above this, a "people affected" figure is almost certainly a typo. It is
#: rejected at the boundary rather than quietly reshaping the priority score.
PEOPLE_AFFECTED_MAX = 10_000


class IncidentCreate(BaseModel):
    category: IncidentCategory
    description: str = Field(min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    location_accuracy_m: int | None = Field(default=None, ge=0, le=100_000)
    address_text: str | None = Field(default=None, max_length=400)
    landmark: str | None = Field(default=None, max_length=200)
    people_affected: int | None = Field(default=None, ge=0, le=PEOPLE_AFFECTED_MAX)
    people_trapped: bool = False
    medical_required: bool = False
    immediate_danger: bool = False
    contact_phone: str | None = Field(default=None, max_length=32)

    @field_validator("description")
    @classmethod
    def _meaningful_description(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < DESCRIPTION_MIN:
            raise ValueError(
                f"Please describe the emergency in at least {DESCRIPTION_MIN} characters."
            )
        return stripped

    @model_validator(mode="after")
    def _trapped_implies_people(self) -> IncidentCreate:
        if self.people_trapped and self.people_affected == 0:
            raise ValueError(
                "people_affected cannot be 0 when people are reported trapped."
            )
        return self


class IncidentUpdate(BaseModel):
    """Operator correction of verified facts. Every field is optional; only
    supplied fields are applied."""

    category: IncidentCategory | None = None
    description: str | None = Field(
        default=None, min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX
    )
    severity: SeverityLevel | None = None
    address_text: str | None = Field(default=None, max_length=400)
    landmark: str | None = Field(default=None, max_length=200)
    people_affected: int | None = Field(default=None, ge=0, le=PEOPLE_AFFECTED_MAX)
    people_trapped: bool | None = None
    medical_required: bool | None = None
    immediate_danger: bool | None = None


class IncidentStatusChange(BaseModel):
    status: IncidentStatus
    note: str | None = Field(default=None, max_length=1000)
    duplicate_of_id: uuid.UUID | None = Field(
        default=None,
        description="Required when moving an incident to DUPLICATE.",
    )

    @model_validator(mode="after")
    def _duplicate_needs_target(self) -> IncidentStatusChange:
        if self.status is IncidentStatus.DUPLICATE and self.duplicate_of_id is None:
            raise ValueError("duplicate_of_id is required for a DUPLICATE transition.")
        if self.status is not IncidentStatus.DUPLICATE and self.duplicate_of_id:
            raise ValueError("duplicate_of_id is only valid for a DUPLICATE transition.")
        return self


class IncidentPriorityUpdate(BaseModel):
    """Recompute, or override with a mandatory reason.

    An override is a human decision that outranks the engine, so it is recorded
    with its justification and shows in the audit log.
    """

    override_band: PriorityBand | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _override_needs_reason(self) -> IncidentPriorityUpdate:
        if self.override_band is not None and not (self.reason or "").strip():
            raise ValueError("A reason is required when overriding priority.")
        return self


class IncidentAssign(BaseModel):
    assigned_to_id: uuid.UUID | None = Field(
        default=None, description="Omit or send null to clear the assignment."
    )
    note: str | None = Field(default=None, max_length=1000)


class PriorityFactorRead(BaseModel):
    key: str
    label: str
    points: int


class IncidentSummary(ORMModel):
    """The list/queue representation."""

    id: uuid.UUID
    reference_code: str
    category: IncidentCategory
    status: IncidentStatus
    severity: SeverityLevel | None
    priority_score: int | None
    priority_band: PriorityBand | None
    priority_overridden: bool
    latitude: Decimal
    longitude: Decimal
    address_text: str | None
    people_affected: int | None
    people_trapped: bool
    medical_required: bool
    immediate_danger: bool
    created_at: datetime
    updated_at: datetime


class IncidentRead(IncidentSummary):
    """The detail representation."""

    description: str
    landmark: str | None
    location_accuracy_m: int | None
    contact_phone: str | None
    priority_factors: list[dict[str, Any]] | None
    priority_override_reason: str | None
    reported_by: UserSummary | None
    assigned_to: UserSummary | None
    duplicate_of_id: uuid.UUID | None
    resolved_at: datetime | None
    closed_at: datetime | None
    media: list[MediaRead] = Field(default_factory=list)


class IncidentStatusHistoryRead(ORMModel):
    id: uuid.UUID
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    note: str | None
    created_at: datetime
    changed_by: UserSummary | None = None


class IncidentStatsSummary(BaseModel):
    """Control-centre header counts."""

    total_open: int
    by_band: dict[str, int]
    by_status: dict[str, int]
    by_category: dict[str, int]
    unassigned_open: int
