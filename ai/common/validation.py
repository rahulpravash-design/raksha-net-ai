"""Validation applied to every AI output before it reaches the database.

Model output is untrusted input. It is validated here, once, so that no caller
has to remember to do it — and so a malformed or implausible response is
rejected whole rather than partially applied.
"""

from __future__ import annotations

from ai.common.schemas import OBSERVATION_VOCABULARY, AnalysisResult

#: Above this a headcount is treated as a model error rather than a report.
PEOPLE_AFFECTED_SANITY_LIMIT = 10_000

#: Below this an analysis is kept but shown de-emphasised, never pre-filled.
LOW_CONFIDENCE_FLOOR = 0.60


class AnalysisRejected(ValueError):
    """Raised when output cannot be trusted enough to store at all."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def validate_analysis(result: AnalysisResult) -> AnalysisResult:
    """Return the result, or raise :class:`AnalysisRejected`.

    Failing closed is the point. A partially-applied analysis would put
    unvalidated numbers in front of a dispatcher with no marker saying which
    fields survived checking.
    """
    reasons: list[str] = []

    if not result.model_name or not result.model_version:
        reasons.append("model_name and model_version are required for traceability")

    if (
        result.people_affected is not None
        and result.people_affected > PEOPLE_AFFECTED_SANITY_LIMIT
    ):
        reasons.append(
            f"people_affected {result.people_affected} exceeds the sanity limit"
        )

    unknown = [
        observation.label
        for observation in result.observations
        if observation.label not in OBSERVATION_VOCABULARY
    ]
    if unknown:
        # A free-text label could assert anything, including a finding the model
        # is not entitled to make.
        reasons.append(f"observations outside the vocabulary: {sorted(unknown)}")

    if result.people_trapped and result.people_affected == 0:
        reasons.append("people_trapped is inconsistent with people_affected of 0")

    if reasons:
        raise AnalysisRejected(reasons)

    return result


def is_low_confidence(result: AnalysisResult) -> bool:
    """True when the UI should de-emphasise this proposal.

    A missing confidence counts as low, never as certainty.
    """
    confidences = [
        value
        for value in (result.type_confidence, result.severity_confidence)
        if value is not None
    ]
    if not confidences:
        return True
    return min(confidences) < LOW_CONFIDENCE_FLOOR
