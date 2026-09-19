"""Resource request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ResourceStatus, ResourceType
from app.schemas.common import ORMModel
from app.schemas.user import UserSummary

CAPABILITY_MAX = 40
CAPABILITIES_MAX_COUNT = 20


class ResourceCreate(BaseModel):
    call_sign: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    resource_type: ResourceType
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    base_address: str | None = Field(default=None, max_length=400)
    capabilities: list[str] = Field(default_factory=list)
    crew_size: int | None = Field(default=None, ge=0, le=1000)
    contact_phone: str | None = Field(default=None, max_length=32)
    operator_id: uuid.UUID | None = None

    @field_validator("call_sign")
    @classmethod
    def _normalise_call_sign(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("capabilities")
    @classmethod
    def _clean_capabilities(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in value if item.strip()]
        if len(cleaned) > CAPABILITIES_MAX_COUNT:
            raise ValueError(f"At most {CAPABILITIES_MAX_COUNT} capabilities.")
        if any(len(item) > CAPABILITY_MAX for item in cleaned):
            raise ValueError(
                f"Each capability must be {CAPABILITY_MAX} characters or fewer."
            )
        return cleaned


class ResourceUpdate(BaseModel):
    """Every field optional; only supplied fields are applied."""

    name: str | None = Field(default=None, min_length=2, max_length=160)
    resource_type: ResourceType | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    base_address: str | None = Field(default=None, max_length=400)
    capabilities: list[str] | None = None
    crew_size: int | None = Field(default=None, ge=0, le=1000)
    contact_phone: str | None = Field(default=None, max_length=32)
    operator_id: uuid.UUID | None = None
    is_active: bool | None = None


class ResourceStatusChange(BaseModel):
    status: ResourceStatus
    note: str | None = Field(default=None, max_length=500)
    #: A unit that has moved reports where it now is, so the next
    #: nearest-unit query is answered from current truth, not its base.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class ResourceRead(ORMModel):
    id: uuid.UUID
    call_sign: str
    name: str
    resource_type: ResourceType
    status: ResourceStatus
    latitude: Decimal
    longitude: Decimal
    base_address: str | None
    capabilities: list[str]
    crew_size: int | None
    contact_phone: str | None
    is_active: bool
    operator: UserSummary | None
    status_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NearbyResource(BaseModel):
    """A resource with its distance from the point that was searched."""

    id: uuid.UUID
    call_sign: str
    name: str
    resource_type: ResourceType
    status: ResourceStatus
    latitude: float
    longitude: float
    capabilities: list[str] = Field(default_factory=list)
    crew_size: int | None = None
    distance_km: float


class ResourceRecommendation(BaseModel):
    """One ranked suggestion for an incident.

    It is a suggestion. Nothing is dispatched until a human says so, and the
    reasons are returned so the dispatcher can disagree with them on sight.
    """

    resource: NearbyResource
    rank: int
    type_match: bool
    matched_capabilities: list[str] = Field(default_factory=list)
    estimated_minutes: int
    reasons: list[str] = Field(default_factory=list)


class ResourceRecommendations(BaseModel):
    incident_id: uuid.UUID
    searched_radius_km: float
    items: list[ResourceRecommendation] = Field(default_factory=list)
    #: Present when nothing matched, so the UI explains rather than showing an
    #: empty list a dispatcher has to interpret under pressure.
    note: str | None = None


class NearbyResources(BaseModel):
    items: list[NearbyResource] = Field(default_factory=list)
    count: int


class ResourceStatsSummary(BaseModel):
    total_active: int
    by_status: dict[str, int]
    by_type: dict[str, int]
