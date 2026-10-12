"""The heuristic text analyzer: keyword extraction, honestly capped confidence,
and agreement with the same validator every analyzer must pass.
"""

from __future__ import annotations

from ai.common.interfaces import AnalyzerUnavailable
from ai.common.schemas import AnalysisRequest
from ai.common.validation import validate_analysis
from ai.nlp.text_analyzer import (
    MAX_SEVERITY_CONFIDENCE,
    MAX_TYPE_CONFIDENCE,
    HeuristicTextAnalyzer,
)

import pytest


def analyze(description: str):
    analyzer = HeuristicTextAnalyzer()
    return analyzer.analyze(
        AnalysisRequest(incident_id="i1", description=description)
    )


def test_a_flood_report_is_classified_as_flood() -> None:
    result = analyze("Water is rising fast and has flooded the ground floor.")
    assert result.incident_type == "FLOOD"
    assert result.type_confidence is not None
    assert result.type_confidence <= MAX_TYPE_CONFIDENCE


def test_a_fire_report_is_classified_as_fire() -> None:
    result = analyze("Flames and heavy smoke are coming from the second floor.")
    assert result.incident_type == "FIRE"


def test_no_keyword_match_leaves_the_type_unknown_rather_than_guessing() -> None:
    result = analyze("Please send someone to check on my neighbour, I am worried.")
    assert result.incident_type is None
    assert result.type_confidence is None


def test_trapped_people_are_detected() -> None:
    result = analyze("Three people are trapped on the roof as water rises.")
    assert result.people_trapped is True
    assert result.people_affected == 3


def test_a_headcount_is_only_extracted_next_to_a_person_word() -> None:
    """A bare number in the text (a house number, a time) is not a headcount."""
    result = analyze("It happened around 4 o'clock near house number 12.")
    assert result.people_affected is None


def test_severity_signals_produce_a_capped_confidence() -> None:
    result = analyze(
        "A child is trapped and not breathing, the fire is spreading rapidly."
    )
    assert result.severity == "CRITICAL"
    assert result.severity_confidence is not None
    assert result.severity_confidence <= MAX_SEVERITY_CONFIDENCE


def test_confidence_never_reaches_certainty() -> None:
    """However many keywords match, a heuristic is never displayed as 100%."""
    result = analyze(
        "Trapped, dying, unconscious, drowning, fire spreading, about to collapse, "
        "child trapped, multiple casualties, not breathing, unable to breathe."
    )
    assert result.type_confidence is None or result.type_confidence < 1.0
    assert result.severity_confidence is not None
    assert result.severity_confidence < 1.0


def test_trapped_with_no_headcount_does_not_imply_zero_people() -> None:
    """The validator rejects trapped=True with people_affected=0; the analyzer
    must never emit that combination in the first place."""
    result = analyze("People are trapped inside, we don't know how many.")
    assert not (result.people_trapped and result.people_affected == 0)


def test_the_result_always_passes_the_shared_validator() -> None:
    result = analyze(
        "A family of 5 is trapped as flood water rises quickly around their house."
    )
    validate_analysis(result)  # raises on failure


def test_observations_are_always_empty_for_a_text_only_analyzer() -> None:
    """This analyzer only reads text; it must never claim a visual finding."""
    result = analyze("The building has collapsed and people are trapped inside.")
    assert result.observations == []


def test_an_empty_description_is_treated_as_unavailable_not_guessed() -> None:
    with pytest.raises(AnalyzerUnavailable):
        analyze("   ")


def test_traceability_fields_are_always_present() -> None:
    result = analyze("A gas leak is reported near the market.")
    assert result.model_name
    assert result.model_version
    assert result.provider == "internal-rules"
    assert result.processing_ms is not None and result.processing_ms >= 0
