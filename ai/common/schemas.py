"""Contracts for AI output.

These are the *only* types the backend knows about. Swapping a model or a
provider must not change anything outside `ai/`.

Nothing here is implemented in V1: `RAKSHA_AI_ENABLED` defaults to false and the
platform ships the :class:`~ai.common.interfaces.NullAnalyzer`. The schemas
exist now so the boundary is real rather than aspirational — code that imports
them cannot quietly start treating inference as fact.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AnalysisSource(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"


class ReviewDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"


#: Fixed vocabulary for vision output.
#:
#: Every label is phrased as an observation, never a finding:
#: ``possible_injured_person``, not ``injured_person``. A model that could emit
#: "injured person present" would be stating as fact something only a responder
#: on scene can establish (``docs/AI_ARCHITECTURE.md`` section 6).
OBSERVATION_VOCABULARY: frozenset[str] = frozenset(
    {
        "standing_water",
        "fast_moving_water",
        "smoke_visible",
        "flames_visible",
        "structural_damage",
        "collapsed_structure",
        "vehicle_involved",
        "crowd_present",
        "possible_injured_person",
        "blocked_road",
        "downed_power_line",
        "darkness_limits_visibility",
    }
)


class Observation(BaseModel):
    """One thing a model believes it can see or hear. Never a verified fact."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="A member of OBSERVATION_VOCABULARY.")
    confidence: float = Field(ge=0.0, le=1.0)
    source: AnalysisSource


class AnalysisResult(BaseModel):
    """Structured information a model proposes from one report.

    ``extra="forbid"`` is deliberate: a model does not get to invent schema, and
    an unexpected key means the output is rejected rather than half-applied.
    """

    model_config = ConfigDict(extra="forbid")

    incident_type: str | None = None
    type_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    severity: str | None = None
    severity_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    people_affected: int | None = Field(default=None, ge=0)
    people_trapped: bool | None = None
    medical_support_required: bool | None = None
    immediate_rescue_required: bool | None = None

    entities: dict[str, list[str]] = Field(default_factory=dict)
    observations: list[Observation] = Field(default_factory=list)
    reasoning_factors: list[str] = Field(default_factory=list)

    model_name: str
    model_version: str
    provider: str | None = None
    processing_ms: int | None = Field(default=None, ge=0)
    created_at: datetime | None = None


class AnalysisRequest(BaseModel):
    """What the backend hands an analyzer.

    Note what is absent: no user id, no contact details, no coordinates. A model
    does not need them, and they must not leak to a third-party provider
    (``docs/AI_ARCHITECTURE.md`` section 11).
    """

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    description: str
    category_hint: str | None = None
    language_hint: str | None = None
    image_bytes: list[bytes] = Field(default_factory=list)
    audio_bytes: bytes | None = None
