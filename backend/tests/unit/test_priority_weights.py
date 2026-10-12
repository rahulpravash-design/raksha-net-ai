"""Versioned priority configuration (Phase 7).

The property under test throughout: tuning the weights must never make a past
score unreadable. A score carries the version that produced it, and that
version's thresholds are what the score is later read back through.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.models.enums import IncidentCategory, PriorityBand
from app.services.priority.config_loader import register_weights_file
from app.services.priority.engine import (
    WEIGHTS_V1,
    PriorityInput,
    band_for_score,
    calculate_priority,
    register_weights,
    resolve_weights,
)


def test_the_default_configuration_is_v1() -> None:
    assert resolve_weights(None) is WEIGHTS_V1
    assert WEIGHTS_V1.version == "1.0.0"


def test_a_score_records_the_configuration_that_produced_it() -> None:
    result = calculate_priority(PriorityInput(category=IncidentCategory.FIRE))
    assert result.engine_version == WEIGHTS_V1.version


def test_custom_weights_change_the_score_and_the_recorded_version() -> None:
    tuned = replace(
        WEIGHTS_V1,
        version="test-2.0.0",
        people_trapped_score=WEIGHTS_V1.people_trapped_score + 10,
    )
    facts = PriorityInput(category=IncidentCategory.FLOOD, people_trapped=True)

    baseline = calculate_priority(facts)
    adjusted = calculate_priority(facts, weights=tuned)

    assert adjusted.score == baseline.score + 10
    assert adjusted.engine_version == "test-2.0.0"


def test_an_unknown_version_is_refused_rather_than_silently_defaulted() -> None:
    """Falling back to the default would misattribute a historical score."""
    with pytest.raises(ValueError, match="Unknown priority engine version"):
        resolve_weights("no-such-version")


def test_reregistering_a_version_with_different_values_is_refused() -> None:
    first = replace(WEIGHTS_V1, version="test-clash", medical_required_score=1)
    second = replace(WEIGHTS_V1, version="test-clash", medical_required_score=2)
    register_weights(first)

    with pytest.raises(ValueError, match="already"):
        register_weights(second)


def test_reregistering_an_identical_version_is_a_no_op() -> None:
    same = replace(WEIGHTS_V1, version="test-idempotent")
    register_weights(same)
    register_weights(same)  # must not raise
    assert resolve_weights("test-idempotent") == same


def test_band_thresholds_come_from_the_configuration() -> None:
    """A re-tuned deployment reads its own history through its own thresholds."""
    strict = replace(
        WEIGHTS_V1,
        version="test-strict",
        band_thresholds=((90, PriorityBand.CRITICAL), (0, PriorityBand.LOW)),
    )
    assert band_for_score(80) is PriorityBand.CRITICAL
    assert band_for_score(80, weights=strict) is PriorityBand.LOW


def test_a_weights_file_is_loaded_and_registered(tmp_path) -> None:
    payload = {
        "version": "test-file-1",
        "band_thresholds": [[70, "CRITICAL"], [40, "HIGH"], [20, "MEDIUM"], [0, "LOW"]],
        "category_base_score": {"FLOOD": 40},
        "default_category_score": 5,
        "severity_score": {"CRITICAL": 20},
        "people_trapped_score": 30,
        "immediate_danger_score": 10,
        "medical_required_score": 10,
        "people_affected_per_person": 2.0,
        "people_affected_cap": 20,
        "people_affected_sanity_limit": 5000,
        "age_score_per_15_min": 1,
        "age_score_cap": 5,
    }
    path = tmp_path / "weights.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    register_weights_file(path)
    loaded = resolve_weights("test-file-1")

    assert loaded.people_trapped_score == 30
    result = calculate_priority(
        PriorityInput(category=IncidentCategory.FLOOD, people_trapped=True),
        weights=loaded,
    )
    assert result.score == 70  # 40 base + 30 trapped
    assert result.band is PriorityBand.CRITICAL
    assert result.engine_version == "test-file-1"


def test_a_malformed_weights_file_fails_loudly(tmp_path) -> None:
    """Starting with the wrong priority configuration silently is the hazard."""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"version": "x", "unknown_field": 1}), encoding="utf-8")

    with pytest.raises(Exception):  # noqa: B017 - pydantic or json, both acceptable
        register_weights_file(path)
