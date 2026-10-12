"""The priority engine is pure, so it is tested exhaustively rather than sampled.

``docs/TESTING.md`` section 3 lists the properties asserted here: isolation of
each factor, band boundaries, monotonicity, determinism, clamping and
explanation completeness.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import IncidentCategory, PriorityBand, SeverityLevel
from app.services.priority.engine import (
    AGE_SCORE_CAP,
    BAND_THRESHOLDS,
    CATEGORY_BASE_SCORE,
    IMMEDIATE_DANGER_SCORE,
    MEDICAL_REQUIRED_SCORE,
    PEOPLE_AFFECTED_CAP,
    PEOPLE_AFFECTED_SANITY_LIMIT,
    PEOPLE_TRAPPED_SCORE,
    SEVERITY_SCORE,
    PriorityInput,
    band_for_score,
    calculate_priority,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def base_input(**overrides: object) -> PriorityInput:
    defaults: dict[str, object] = {"category": IncidentCategory.OTHER}
    defaults.update(overrides)
    return PriorityInput(**defaults)  # type: ignore[arg-type]


# --- factors in isolation ----------------------------------------------------
@pytest.mark.parametrize("category", list(IncidentCategory))
def test_every_category_has_a_base_score(category: IncidentCategory) -> None:
    result = calculate_priority(base_input(category=category))
    assert result.score == CATEGORY_BASE_SCORE[category]
    assert result.factors[0].key == "category"


@pytest.mark.parametrize("severity", list(SeverityLevel))
def test_severity_contributes_its_weight(severity: SeverityLevel) -> None:
    baseline = calculate_priority(base_input()).score
    result = calculate_priority(base_input(severity=severity))
    assert result.score == baseline + SEVERITY_SCORE[severity]


def test_people_trapped_contributes_its_weight() -> None:
    baseline = calculate_priority(base_input()).score
    result = calculate_priority(base_input(people_trapped=True))
    assert result.score == baseline + PEOPLE_TRAPPED_SCORE
    assert any(f.key == "people_trapped" for f in result.factors)


def test_immediate_danger_contributes_its_weight() -> None:
    baseline = calculate_priority(base_input()).score
    assert (
        calculate_priority(base_input(immediate_danger=True)).score
        == baseline + IMMEDIATE_DANGER_SCORE
    )


def test_medical_required_contributes_its_weight() -> None:
    baseline = calculate_priority(base_input()).score
    assert (
        calculate_priority(base_input(medical_required=True)).score
        == baseline + MEDICAL_REQUIRED_SCORE
    )


# --- people affected ---------------------------------------------------------
@pytest.mark.parametrize(
    ("people", "expected"),
    [(None, 0), (0, 0), (1, 1), (2, 3), (5, 7), (10, PEOPLE_AFFECTED_CAP)],
)
def test_people_affected_scales_then_caps(people: int | None, expected: int) -> None:
    baseline = calculate_priority(base_input()).score
    assert (
        calculate_priority(base_input(people_affected=people)).score
        == baseline + expected
    )


def test_implausible_headcount_contributes_only_the_cap() -> None:
    """A data-entry error must not be able to distort the ranking."""
    baseline = calculate_priority(base_input()).score
    result = calculate_priority(
        base_input(people_affected=PEOPLE_AFFECTED_SANITY_LIMIT + 1_000_000)
    )
    assert result.score == baseline + PEOPLE_AFFECTED_CAP


def test_headcount_never_outranks_life_safety() -> None:
    """A large but stable incident must not outrank a small life-threatening one."""
    crowd = calculate_priority(
        base_input(category=IncidentCategory.OTHER, people_affected=500)
    )
    trapped = calculate_priority(
        base_input(
            category=IncidentCategory.BUILDING_COLLAPSE,
            people_trapped=True,
            immediate_danger=True,
            people_affected=1,
        )
    )
    assert trapped.score > crowd.score


# --- waiting time ------------------------------------------------------------
@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, 0), (14, 0), (15, 2), (30, 4), (60, 8), (600, AGE_SCORE_CAP)],
)
def test_waiting_time_accrues_then_caps(minutes: int, expected: int) -> None:
    baseline = calculate_priority(base_input()).score
    result = calculate_priority(
        base_input(reported_at=NOW - timedelta(minutes=minutes)), now=NOW
    )
    assert result.score == baseline + expected


def test_waiting_time_is_ignored_without_a_reference_time() -> None:
    """The engine is pure: with no ``now`` there is no age contribution."""
    result = calculate_priority(base_input(reported_at=NOW - timedelta(hours=5)))
    assert all(f.key != "waiting_time" for f in result.factors)


def test_future_report_time_does_not_reduce_the_score() -> None:
    baseline = calculate_priority(base_input()).score
    result = calculate_priority(base_input(reported_at=NOW + timedelta(hours=1)), now=NOW)
    assert result.score == baseline


# --- bands -------------------------------------------------------------------
@pytest.mark.parametrize(("threshold", "band"), BAND_THRESHOLDS)
def test_band_boundaries(threshold: int, band: PriorityBand) -> None:
    assert band_for_score(threshold) is band
    assert band_for_score(threshold + 1) is band or threshold + 1 >= BAND_THRESHOLDS[0][0]
    if threshold > 0:
        assert band_for_score(threshold - 1) is not band


def test_band_for_every_score_in_range() -> None:
    assert all(band_for_score(score) in set(PriorityBand) for score in range(0, 101))


def test_critical_scenario_reaches_critical() -> None:
    result = calculate_priority(
        PriorityInput(
            category=IncidentCategory.FLOOD,
            severity=SeverityLevel.CRITICAL,
            people_affected=5,
            people_trapped=True,
            medical_required=True,
            immediate_danger=True,
        )
    )
    assert result.band is PriorityBand.CRITICAL


def test_minor_scenario_stays_low() -> None:
    result = calculate_priority(
        PriorityInput(category=IncidentCategory.OTHER, severity=SeverityLevel.LOW)
    )
    assert result.band is PriorityBand.LOW


# --- invariants --------------------------------------------------------------
def test_score_is_clamped_to_the_valid_range() -> None:
    result = calculate_priority(
        PriorityInput(
            category=IncidentCategory.BUILDING_COLLAPSE,
            severity=SeverityLevel.CRITICAL,
            people_affected=10_000,
            people_trapped=True,
            medical_required=True,
            immediate_danger=True,
            reported_at=NOW - timedelta(days=2),
        ),
        now=NOW,
    )
    assert 0 <= result.score <= 100


@pytest.mark.parametrize(
    "aggravating",
    [
        {"people_trapped": True},
        {"immediate_danger": True},
        {"medical_required": True},
        {"people_affected": 3},
        {"severity": SeverityLevel.CRITICAL},
    ],
)
def test_adding_an_aggravating_fact_never_lowers_the_score(
    aggravating: dict[str, object],
) -> None:
    before = calculate_priority(base_input(category=IncidentCategory.FIRE)).score
    after = calculate_priority(
        base_input(category=IncidentCategory.FIRE, **aggravating)
    ).score
    assert after >= before


def test_engine_is_deterministic() -> None:
    data = PriorityInput(
        category=IncidentCategory.MEDICAL,
        severity=SeverityLevel.HIGH,
        people_affected=2,
        medical_required=True,
        reported_at=NOW - timedelta(minutes=45),
    )
    first = calculate_priority(data, now=NOW)
    second = calculate_priority(data, now=NOW)
    assert first.score == second.score
    assert first.band is second.band
    assert first.factors_as_json() == second.factors_as_json()


def test_every_contribution_is_explained() -> None:
    """A score the control centre cannot explain is not usable evidence."""
    result = calculate_priority(
        PriorityInput(
            category=IncidentCategory.FIRE,
            severity=SeverityLevel.HIGH,
            people_affected=4,
            people_trapped=True,
            medical_required=True,
            immediate_danger=True,
            reported_at=NOW - timedelta(minutes=30),
        ),
        now=NOW,
    )
    assert sum(f.points for f in result.factors) >= result.score
    assert {f.key for f in result.factors} == {
        "category",
        "severity",
        "people_trapped",
        "immediate_danger",
        "medical_required",
        "people_affected",
        "waiting_time",
    }
    assert result.explanation()


def test_result_serialises_for_storage() -> None:
    result = calculate_priority(base_input(people_trapped=True))
    payload = result.factors_as_json()
    assert all(set(item) == {"key", "label", "points"} for item in payload)
