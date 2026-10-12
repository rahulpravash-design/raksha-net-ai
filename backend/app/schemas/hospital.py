"""Hospital and inbound-notice schemas.

``InboundNoticeRead`` is the data-minimisation boundary in code: it is the
complete set of fields a hospital ever receives about an incident, and it has
no field for the reporter, their contact details, or the report text.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    HospitalNoticeStatus,
    IncidentCategory,
    SeverityLevel,
)
from app.schemas.common import ORMModel
from app.schemas.user import UserSummary


class HospitalCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = Field(default=None, max_length=400)
    contact_phone: str | None = Field(default=None, max_length=32)
    total_beds: int = Field(default=0, ge=0, le=100_000)
    available_beds: int = Field(default=0, ge=0, le=100_000)
    icu_total: int = Field(default=0, ge=0, le=100_000)
    icu_available: int = Field(default=0, ge=0, le=100_000)
    specialties: list[str] = Field(default_factory=list)
    managed_by_id: uuid.UUID | None = None

    @field_validator("code")
    @classmethod
    def _upper_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _available_within_total(self) -> HospitalCreate:
        if self.available_beds > self.total_beds:
            raise ValueError("available_beds cannot exceed total_beds.")
        if self.icu_available > self.icu_total:
            raise ValueError("icu_available cannot exceed icu_total.")
        return self


class HospitalUpdate(BaseModel):
    """Administrator corrections to what a hospital *is* (not how full it is).

    The code is the hospital's identity and is not editable; capacity has its own
    endpoint and its own, wider, set of people who may use it. ``extra="forbid"``
    so an attempt to change either is refused rather than quietly ignored.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, max_length=400)
    contact_phone: str | None = Field(default=None, max_length=32)
    #: ``null`` unlinks the operator; leaving the key out keeps the current one.
    managed_by_id: uuid.UUID | None = None
    #: Retire a hospital (or bring it back). Refused while it has open notices.
    is_active: bool | None = None


class HospitalCapacityUpdate(BaseModel):
    """What a hospital operator reports, several times a shift."""

    available_beds: int | None = Field(default=None, ge=0, le=100_000)
    icu_available: int | None = Field(default=None, ge=0, le=100_000)
    total_beds: int | None = Field(default=None, ge=0, le=100_000)
    icu_total: int | None = Field(default=None, ge=0, le=100_000)
    accepting_emergencies: bool | None = None
    specialties: list[str] | None = None
    note: str | None = Field(default=None, max_length=500)


class HospitalRead(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    latitude: Decimal
    longitude: Decimal
    address: str | None
    contact_phone: str | None
    total_beds: int
    available_beds: int
    icu_total: int
    icu_available: int
    accepting_emergencies: bool
    specialties: list[str]
    is_active: bool
    managed_by: UserSummary | None
    capacity_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NearbyHospital(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    latitude: float
    longitude: float
    available_beds: int
    icu_available: int
    accepting_emergencies: bool
    specialties: list[str] = Field(default_factory=list)
    contact_phone: str | None = None
    distance_km: float


class NearbyHospitals(BaseModel):
    items: list[NearbyHospital] = Field(default_factory=list)
    count: int


class InboundNoticeCreate(BaseModel):
    """Everything a dispatcher may send a hospital.

    There is no field here for the reporter or the report text. A dispatcher
    who needs to pass on a clinical detail writes it into ``clinical_notes``
    deliberately, rather than the citizen's words travelling by default.
    """

    hospital_id: uuid.UUID
    patient_count: int = Field(default=1, ge=1, le=1000)
    severity: SeverityLevel | None = None
    eta_minutes: int | None = Field(default=None, ge=0, le=1440)
    clinical_notes: str | None = Field(default=None, max_length=1000)
    dispatch_id: uuid.UUID | None = None


class InboundNoticeStatusChange(BaseModel):
    status: HospitalNoticeStatus
    response_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _divert_needs_a_note(self) -> InboundNoticeStatusChange:
        if (
            self.status is HospitalNoticeStatus.DIVERTED
            and not (self.response_note or "").strip()
        ):
            raise ValueError("A note is required when diverting an inbound patient.")
        return self


class InboundNoticeRead(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    incident_id: uuid.UUID
    dispatch_id: uuid.UUID | None
    status: HospitalNoticeStatus
    patient_count: int
    category: IncidentCategory
    severity: SeverityLevel | None
    eta_minutes: int | None
    clinical_notes: str | None
    response_note: str | None
    created_by: UserSummary
    acknowledged_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
