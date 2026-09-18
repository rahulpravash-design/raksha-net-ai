"""The deterministic emergency priority engine.

This module is the reason the platform can be audited. It is a **pure
function**: given a set of facts and a reference time, it returns the same
score, band and explanation every time. It performs no I/O, reads no clock and
calls no model.

An LLM never sets operational priority (``CLAUDE.md`` section 2, rule 5). AI may
propose facts; a human accepts them; this engine scores what was accepted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models.enums import IncidentCategory, PriorityBand, SeverityLevel

#: Configuration version recorded alongside every score, so a historical
#: decision can be reproduced after the weights change.
ENGINE_VERSION = "1.0.0"

MIN_SCORE = 0
MAX_SCORE = 100

#: Score at or above which each band begins. Checked in descending order.
BAND_THRESHOLDS: tuple[tuple[int, PriorityBand], ...] = (
    (75, PriorityBand.CRITICAL),
    (50, PriorityBand.HIGH),
    (25, PriorityBand.MEDIUM),
    (MIN_SCORE, PriorityBand.LOW),
)

#: Inherent urgency of a category before any situational fact is considered.
CATEGORY_BASE_SCORE: dict[IncidentCategory, int] = {
    IncidentCategory.MEDICAL: 30,
    IncidentCategory.FIRE: 30,
    IncidentCategory.BUILDING_COLLAPSE: 32,
    IncidentCategory.GAS_LEAK: 28,
    IncidentCategory.ROAD_ACCIDENT: 25,
    IncidentCategory.FLOOD: 24,
    IncidentCategory.LANDSLIDE: 26,
    IncidentCategory.INDUSTRIAL_ACCIDENT: 26,
    IncidentCategory.ELECTRICAL_HAZARD: 20,
    IncidentCategory.MISSING_PERSON: 18,
    IncidentCategory.OTHER: 12,
}
DEFAULT_CATEGORY_SCORE = 12

SEVERITY_SCORE: dict[SeverityLevel, int] = {
    SeverityLevel.CRITICAL: 25,
    SeverityLevel.HIGH: 16,
    SeverityLevel.MODERATE: 8,
    SeverityLevel.LOW: 0,
}

PEOPLE_TRAPPED_SCORE = 22
IMMEDIATE_DANGER_SCORE = 16
MEDICAL_REQUIRED_SCORE = 12

#: Scale factor per person affected, capped so that a large-but-stable incident
#: never outranks a small life-threatening one on headcount alone.
PEOPLE_AFFECTED_PER_PERSON = 1.5
PEOPLE_AFFECTED_CAP = 15

#: An incident that has waited without triage gains urgency. The cap keeps age
#: from ever dominating the life-safety factors above.
AGE_SCORE_PER_15_MIN = 2
AGE_SCORE_CAP = 10

#: Sanity ceiling: a value above this is treated as a data-entry error rather
#: than being allowed to distort the score.
PEOPLE_AFFECTED_SANITY_LIMIT = 10_000


@dataclass(frozen=True, slots=True)
class PriorityFactor:
    """One contribution to the score, kept so the result can be explained."""

    key: str
    label: str
    points: int

    def to_dict(self) -> dict[str, object]:
        return {"key": self.key, "label": self.label, "points": self.points}


@dataclass(frozen=True, slots=True)
class PriorityInput:
    """The facts the engine scores.

    Only facts reach this object. Anything AI-derived must have been reviewed
    and accepted by a human before it is placed here.
    """

    category: IncidentCategory
    severity: SeverityLevel | None = None
    people_affected: int | None = None
    people_trapped: bool = False
    medical_required: bool = False
    immediate_danger: bool = False
    reported_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PriorityResult:
    score: int
    band: PriorityBand
    factors: list[PriorityFactor] = field(default_factory=list)
    engine_version: str = ENGINE_VERSION

    def factors_as_json(self) -> list[dict[str, object]]:
        return [factor.to_dict() for factor in self.factors]

    def explanation(self) -> str:
        parts = [f"{f.label} (+{f.points})" for f in self.factors if f.points]
        return "; ".join(parts) if parts else "No aggravating factors recorded."


def band_for_score(score: int) -> PriorityBand:
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return PriorityBand.LOW  # pragma: no cover - unreachable, the last threshold is 0


def calculate_priority(
    data: PriorityInput, *, now: datetime | None = None
) -> PriorityResult:
    """Score an incident from 0 to 100 and explain the result.

    ``now`` is a parameter rather than a call to the clock so the function stays
    pure and the age factor is testable.
    """
    factors: list[PriorityFactor] = []

    base = CATEGORY_BASE_SCORE.get(data.category, DEFAULT_CATEGORY_SCORE)
    factors.append(
        PriorityFactor(
            key="category",
            label=f"Incident category: {data.category.value.replace('_', ' ').title()}",
            points=base,
        )
    )

    if data.severity is not None:
        points = SEVERITY_SCORE.get(data.severity, 0)
        if points:
            factors.append(
                PriorityFactor(
                    key="severity",
                    label=f"Assessed severity: {data.severity.value.title()}",
                    points=points,
                )
            )

    if data.people_trapped:
        factors.append(
            PriorityFactor(
                key="people_trapped",
                label="People are reported trapped",
                points=PEOPLE_TRAPPED_SCORE,
            )
        )

    if data.immediate_danger:
        factors.append(
            PriorityFactor(
                key="immediate_danger",
                label="Immediate danger to life reported",
                points=IMMEDIATE_DANGER_SCORE,
            )
        )

    if data.medical_required:
        factors.append(
            PriorityFactor(
                key="medical_required",
                label="Medical support required",
                points=MEDICAL_REQUIRED_SCORE,
            )
        )

    people_points = _people_affected_points(data.people_affected)
    if people_points:
        factors.append(
            PriorityFactor(
                key="people_affected",
                label=f"{data.people_affected} people reported affected",
                points=people_points,
            )
        )

    age_points = _age_points(data.reported_at, now)
    if age_points:
        factors.append(
            PriorityFactor(
                key="waiting_time",
                label="Incident has been waiting for triage",
                points=age_points,
            )
        )

    total = sum(factor.points for factor in factors)
    score = max(MIN_SCORE, min(MAX_SCORE, total))

    return PriorityResult(score=score, band=band_for_score(score), factors=factors)


def _people_affected_points(people_affected: int | None) -> int:
    if people_affected is None or people_affected <= 0:
        return 0
    if people_affected > PEOPLE_AFFECTED_SANITY_LIMIT:
        # Implausible input contributes the cap rather than distorting the score.
        return PEOPLE_AFFECTED_CAP
    return min(PEOPLE_AFFECTED_CAP, int(people_affected * PEOPLE_AFFECTED_PER_PERSON))


def _age_points(reported_at: datetime | None, now: datetime | None) -> int:
    if reported_at is None or now is None:
        return 0
    elapsed = now - reported_at
    if elapsed <= timedelta(0):
        return 0
    quarter_hours = int(elapsed.total_seconds() // 900)
    return min(AGE_SCORE_CAP, quarter_hours * AGE_SCORE_PER_15_MIN)
