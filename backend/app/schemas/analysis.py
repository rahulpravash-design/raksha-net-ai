"""AI analysis proposal and review schemas.

``IncidentAnalysisRead`` is deliberately never embedded inside ``IncidentRead``:
CLAUDE.md section 2, rule 2 requires AI output to be stored, and returned,
separately from verified facts, so a client cannot casually render a proposal
where it would read as a confirmed fact.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AnalysisReviewDecision, IncidentCategory, SeverityLevel
from app.schemas.common import ORMModel
from app.schemas.user import UserSummary

PEOPLE_AFFECTED_MAX = 10_000


class AnalysisObservationRead(BaseModel):
    label: str
    confidence: float
    source: str


class IncidentAnalysisRead(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    model_name: str
    model_version: str
    provider: str | None
    processing_ms: int | None

    proposed_category: IncidentCategory | None
    type_confidence: float | None
    proposed_severity: SeverityLevel | None
    severity_confidence: float | None
    people_affected: int | None
    people_trapped: bool | None
    medical_support_required: bool | None
    immediate_rescue_required: bool | None
    entities: dict[str, list[str]]
    observations: list[AnalysisObservationRead]
    reasoning_factors: list[str]

    review_decision: AnalysisReviewDecision | None
    reviewed_by: UserSummary | None
    reviewed_at: datetime | None
    review_note: str | None
    applied_fields: dict[str, Any] | None
    created_at: datetime


class AnalysisReview(BaseModel):
    """A dispatcher's disposition of one AI proposal.

    ``ACCEPTED`` applies the proposal's own values to the incident. ``EDITED``
    applies the values supplied here instead — the dispatcher's correction, not
    the model's guess. ``REJECTED`` changes nothing on the incident; only the
    review itself is recorded, so the proposal is never silently discarded
    without a trace (CLAUDE.md section 5: every sensitive action is audited).
    """

    decision: AnalysisReviewDecision
    note: str | None = Field(default=None, max_length=1000)
    category: IncidentCategory | None = None
    severity: SeverityLevel | None = None
    people_affected: int | None = Field(default=None, ge=0, le=PEOPLE_AFFECTED_MAX)
    people_trapped: bool | None = None
    medical_required: bool | None = None
    immediate_danger: bool | None = None

    @model_validator(mode="after")
    def _edit_needs_a_value(self) -> AnalysisReview:
        if self.decision is AnalysisReviewDecision.EDITED and not any(
            value is not None
            for value in (
                self.category,
                self.severity,
                self.people_affected,
                self.people_trapped,
                self.medical_required,
                self.immediate_danger,
            )
        ):
            raise ValueError("An edited review must supply at least one corrected value.")
        return self
