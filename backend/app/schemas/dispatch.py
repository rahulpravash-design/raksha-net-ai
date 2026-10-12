"""Dispatch request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DispatchStatus, IncidentCategory, PriorityBand
from app.schemas.common import ORMModel
from app.schemas.resource import ResourceRead
from app.schemas.user import UserSummary


class DispatchCreate(BaseModel):
    """Commit a resource to an incident.

    There is no ``approved_by`` field: the approver is the authenticated
    dispatcher making the call, never a value the client can supply.
    """

    resource_id: uuid.UUID
    note: str | None = Field(default=None, max_length=1000)


class DispatchStatusChange(BaseModel):
    status: DispatchStatus
    note: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _cancel_needs_a_reason(self) -> DispatchStatusChange:
        if self.status is DispatchStatus.CANCELLED and not (self.reason or "").strip():
            raise ValueError("A reason is required when cancelling a dispatch.")
        return self


class DispatchIncidentBrief(ORMModel):
    """What a responder needs to reach the scene and nothing more.

    The reporter's identity is deliberately absent (``docs/SECURITY.md``:
    precise personal data goes only where it is operationally needed).
    """

    id: uuid.UUID
    reference_code: str
    category: IncidentCategory
    priority_band: PriorityBand | None
    description: str
    latitude: float
    longitude: float
    address_text: str | None
    landmark: str | None
    people_affected: int | None
    people_trapped: bool
    medical_required: bool
    immediate_danger: bool
    contact_phone: str | None


class DispatchRead(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    resource_id: uuid.UUID
    status: DispatchStatus
    distance_km: float | None
    estimated_minutes: int | None
    note: str | None
    cancel_reason: str | None
    approved_by: UserSummary
    resource: ResourceRead
    acknowledged_at: datetime | None
    en_route_at: datetime | None
    on_scene_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResponderAssignment(DispatchRead):
    """A dispatch as the responder application shows it, with the scene brief."""

    incident: DispatchIncidentBrief
