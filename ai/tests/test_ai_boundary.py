"""The AI boundary must hold even though no model is implemented.

These tests exist in V1 on purpose: the safety rules in ``CLAUDE.md`` section 2
are only real if something enforces them before the first model arrives.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai.common import (
    OBSERVATION_VOCABULARY,
    AnalysisRejected,
    AnalysisRequest,
    AnalysisResult,
    AnalysisSource,
    AnalyzerUnavailable,
    NullAnalyzer,
    Observation,
    get_analyzer,
    is_low_confidence,
    validate_analysis,
)


def result(**overrides: object) -> AnalysisResult:
    payload: dict[str, object] = {
        "model_name": "test-model",
        "model_version": "0.1.0",
    }
    payload.update(overrides)
    return AnalysisResult(**payload)  # type: ignore[arg-type]


# --- the disabled path -------------------------------------------------------
def test_the_default_analyzer_declines_rather_than_guessing() -> None:
    analyzer = get_analyzer(enabled=False)
    assert isinstance(analyzer, NullAnalyzer)

    with pytest.raises(AnalyzerUnavailable):
        analyzer.analyze(
            AnalysisRequest(incident_id="i1", description="Water is rising.")
        )


def test_enabling_ai_without_an_implementation_fails_loudly() -> None:
    """Silently falling back to "no analysis" would hide a misconfiguration."""
    with pytest.raises(NotImplementedError):
        get_analyzer(enabled=True)


def test_a_request_carries_no_personal_data() -> None:
    """A model needs the situation, not the reporter's identity or location."""
    fields = set(AnalysisRequest.model_fields)
    assert not fields & {
        "user_id",
        "reported_by",
        "contact_phone",
        "latitude",
        "longitude",
        "email",
    }


# --- output contract ---------------------------------------------------------
def test_traceability_fields_are_mandatory() -> None:
    with pytest.raises(ValidationError):
        AnalysisResult()  # type: ignore[call-arg]


def test_unknown_fields_are_refused() -> None:
    """A model does not get to invent schema."""
    with pytest.raises(ValidationError):
        AnalysisResult(
            model_name="m", model_version="1", dispatch_ambulance=True  # type: ignore[call-arg]
        )


def test_the_result_has_no_field_that_could_dispatch_anything() -> None:
    """AI proposes; a human disposes (CLAUDE.md section 2, rule 1)."""
    fields = set(AnalysisResult.model_fields)
    assert not fields & {
        "priority_score",
        "priority_band",
        "assigned_to",
        "dispatch",
        "resource_id",
        "status",
    }


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_confidence_must_be_a_probability(value: float) -> None:
    with pytest.raises(ValidationError):
        result(type_confidence=value)


def test_a_negative_headcount_is_refused() -> None:
    with pytest.raises(ValidationError):
        result(people_affected=-1)


# --- vocabulary --------------------------------------------------------------
def test_every_observation_label_is_phrased_as_an_observation() -> None:
    """No label may assert a finding only a responder on scene can make."""
    forbidden = {"injured_person", "fire_confirmed", "flood_confirmed", "fatality"}
    assert not OBSERVATION_VOCABULARY & forbidden
    assert "possible_injured_person" in OBSERVATION_VOCABULARY


def test_a_free_text_observation_is_rejected() -> None:
    with pytest.raises(AnalysisRejected):
        validate_analysis(
            result(
                observations=[
                    Observation(
                        label="two people are definitely dead",
                        confidence=0.99,
                        source=AnalysisSource.IMAGE,
                    )
                ]
            )
        )


def test_a_vocabulary_observation_passes() -> None:
    validated = validate_analysis(
        result(
            observations=[
                Observation(
                    label="standing_water",
                    confidence=0.91,
                    source=AnalysisSource.IMAGE,
                )
            ]
        )
    )
    assert validated.observations[0].label == "standing_water"


# --- validation --------------------------------------------------------------
def test_an_implausible_headcount_is_rejected_not_clamped() -> None:
    with pytest.raises(AnalysisRejected) as excinfo:
        validate_analysis(result(people_affected=5_000_000))
    assert "sanity limit" in str(excinfo.value)


def test_internally_inconsistent_output_is_rejected() -> None:
    with pytest.raises(AnalysisRejected):
        validate_analysis(result(people_trapped=True, people_affected=0))


def test_missing_traceability_is_rejected_by_the_validator_too() -> None:
    bare = result()
    bare = bare.model_copy(update={"model_version": ""})
    with pytest.raises(AnalysisRejected):
        validate_analysis(bare)


def test_all_reasons_are_reported_together() -> None:
    bad = result(
        people_affected=5_000_000,
        observations=[
            Observation(label="not_a_label", confidence=0.5, source=AnalysisSource.TEXT)
        ],
    )
    with pytest.raises(AnalysisRejected) as excinfo:
        validate_analysis(bad)

    # Both problems are reported at once, so a caller fixing one does not have
    # to discover the next on the following attempt.
    assert len(excinfo.value.reasons) == 2


# --- confidence --------------------------------------------------------------
def test_absent_confidence_counts_as_low_not_as_certainty() -> None:
    assert is_low_confidence(result()) is True


def test_low_confidence_is_flagged() -> None:
    assert is_low_confidence(result(type_confidence=0.4, severity_confidence=0.9))


def test_high_confidence_is_not_flagged() -> None:
    assert not is_low_confidence(result(type_confidence=0.95, severity_confidence=0.88))
