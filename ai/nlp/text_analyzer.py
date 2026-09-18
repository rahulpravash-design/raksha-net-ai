"""A rule-based text analyzer: the V2 baseline for :class:`EmergencyAnalyzer`.

``docs/AI_ARCHITECTURE.md`` section 7 is explicit that a simple baseline ships
first in every stage, "so there is always a measurable reference point and a
working fallback." This is that baseline for text classification and entity
extraction: keyword and regex matching, not a trained model.

That is a deliberate, not a temporary, choice for this environment: a trained
classifier needs a labelled dataset (``docs/ROADMAP.md`` Phase 6 lists one as
a dependency) and an evaluation harness (``docs/AI_ARCHITECTURE.md`` section 9)
that do not exist yet, and an LLM-backed extractor needs a provider contract
this deployment has not been given. Shipping a heuristic honestly, with capped
confidence and full reasoning transparency, is safer than shipping a model that
has not been evaluated. Swapping this module for a trained one later changes
nothing outside ``ai/`` (``docs/AI_ARCHITECTURE.md`` section 10).
"""

from __future__ import annotations

import re
import time

from ai.common.interfaces import AnalyzerUnavailable
from ai.common.schemas import AnalysisRequest, AnalysisResult

MODEL_NAME = "raksha-heuristic-text-analyzer"
MODEL_VERSION = "0.1.0"
PROVIDER = "internal-rules"

#: A heuristic keyword match is never certain. Capping confidence below 1.0
#: keeps a rule-based guess from being displayed with the same weight as a
#: calibrated model (``docs/AI_ARCHITECTURE.md`` section 5).
MAX_TYPE_CONFIDENCE = 0.78
MAX_SEVERITY_CONFIDENCE = 0.72

#: Category keyword table. Values are plain strings, matching
#: ``app.models.enums.IncidentCategory`` by construction, but this module does
#: not import the backend enum: ``ai/`` does not depend on ``backend/``
#: (``CLAUDE.md`` section 4, rule 5).
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "FLOOD": (
        "flood",
        "flooding",
        "water rising",
        "water is rising",
        "rising water",
        "waterlogged",
        "submerged",
        "overflow",
    ),
    "FIRE": ("fire", "flames", "burning", "smoke", "blaze"),
    "ROAD_ACCIDENT": (
        "accident",
        "collision",
        "crash",
        "hit by a vehicle",
        "overturned",
        "car crash",
    ),
    "MEDICAL": (
        "unconscious",
        "not breathing",
        "heart attack",
        "seizure",
        "bleeding heavily",
        "medical emergency",
        "labour pain",
        "labor pain",
    ),
    "BUILDING_COLLAPSE": (
        "collapsed",
        "collapse",
        "building fell",
        "roof caved",
        "wall collapsed",
        "structure collapsed",
    ),
    "MISSING_PERSON": ("missing", "not found", "gone missing", "cannot locate", "lost child"),
    "LANDSLIDE": ("landslide", "mudslide", "hillside gave way", "debris flow"),
    "INDUSTRIAL_ACCIDENT": (
        "factory",
        "industrial accident",
        "machinery",
        "chemical spill",
        "explosion at the plant",
    ),
    "GAS_LEAK": ("gas leak", "gas smell", "smell of gas", "cylinder leaking"),
    "ELECTRICAL_HAZARD": (
        "electrocuted",
        "live wire",
        "downed power line",
        "sparking wire",
        "electric shock",
    ),
}

#: Severity signal keywords, each with a point weight. Summed and clamped, not
#: used to assert a fact — only to propose where a human should look first.
_CRITICAL_SIGNALS: tuple[str, ...] = (
    "trapped",
    "dying",
    "not breathing",
    "unconscious",
    "unable to breathe",
    "drowning",
    "fire spreading",
    "about to collapse",
    "child trapped",
    "multiple casualties",
)
_HIGH_SIGNALS: tuple[str, ...] = (
    "injured",
    "bleeding",
    "urgent",
    "rising fast",
    "spreading",
    "collapsed",
    "cannot escape",
    "surrounded by water",
)
_MODERATE_SIGNALS: tuple[str, ...] = (
    "damaged",
    "blocked",
    "stuck",
    "smoke",
    "minor injury",
    "shaken",
)

_MEDICAL_SIGNALS: tuple[str, ...] = (
    "injured",
    "bleeding",
    "unconscious",
    "hurt",
    "not breathing",
    "pain",
    "wound",
)
_RESCUE_SIGNALS: tuple[str, ...] = (
    "trapped",
    "rising fast",
    "spreading",
    "about to collapse",
    "cannot escape",
    "drowning",
    "surrounded by water",
)

_WORD_NUMBERS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_NUMBER_TOKEN = r"(?:\d{1,4}|" + "|".join(_WORD_NUMBERS) + r")"

#: "5 people", "a family of 4", "three members" - deliberately conservative: it
#: matches a number (digit or spelled out up to ten) next to a person-word, not
#: any number in the text.
_HEADCOUNT_PATTERN = re.compile(
    rf"\b({_NUMBER_TOKEN})\s*(?:people|persons?|members?|individuals?|children|kids|villagers)\b",
    re.IGNORECASE,
)
_TRAPPED_PATTERN = re.compile(r"\btrapped\b", re.IGNORECASE)


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def _score_categories(text: str) -> tuple[str | None, float | None, list[str]]:
    best_category: str | None = None
    best_hits = 0
    matched_phrases: list[str] = []

    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in text]
        if len(hits) > best_hits:
            best_hits = len(hits)
            best_category = category
            matched_phrases = hits

    if best_category is None or best_hits == 0:
        return None, None, []

    # More independent keyword hits raise confidence, but it never reaches the
    # cap: a handful of keyword matches is evidence, not certainty.
    confidence = min(MAX_TYPE_CONFIDENCE, 0.45 + 0.15 * best_hits)
    reasons = [f"description mentions '{phrase}'" for phrase in matched_phrases]
    return best_category, round(confidence, 2), reasons


def _score_severity(text: str) -> tuple[str | None, float | None, list[str]]:
    critical_hits = [word for word in _CRITICAL_SIGNALS if word in text]
    high_hits = [word for word in _HIGH_SIGNALS if word in text]
    moderate_hits = [word for word in _MODERATE_SIGNALS if word in text]

    if critical_hits:
        confidence = min(MAX_SEVERITY_CONFIDENCE, 0.5 + 0.1 * len(critical_hits))
        reasons = [f"description mentions '{phrase}'" for phrase in critical_hits]
        return "CRITICAL", round(confidence, 2), reasons
    if high_hits:
        confidence = min(MAX_SEVERITY_CONFIDENCE, 0.45 + 0.08 * len(high_hits))
        reasons = [f"description mentions '{phrase}'" for phrase in high_hits]
        return "HIGH", round(confidence, 2), reasons
    if moderate_hits:
        confidence = min(MAX_SEVERITY_CONFIDENCE, 0.4 + 0.05 * len(moderate_hits))
        reasons = [f"description mentions '{phrase}'" for phrase in moderate_hits]
        return "MODERATE", round(confidence, 2), reasons
    return None, None, []


def _extract_people_affected(text: str) -> int | None:
    match = _HEADCOUNT_PATTERN.search(text)
    if not match:
        return None
    token = match.group(1).lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


class HeuristicTextAnalyzer:
    """Keyword- and regex-based extraction from a report's own description.

    No network call, no third-party provider, and nothing here ever sees a
    reporter's identity or coordinates (``AnalysisRequest`` does not carry
    them). Vision and audio are not implemented: ``observations`` is always
    empty, since this analyzer only ever reads text.
    """

    name = MODEL_NAME
    version = MODEL_VERSION

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        text = _normalise(request.description)
        if not text:
            raise AnalyzerUnavailable("The report has no description to analyse.")

        started = time.perf_counter()

        incident_type, type_confidence, type_reasons = _score_categories(text)
        severity, severity_confidence, severity_reasons = _score_severity(text)
        people_affected = _extract_people_affected(text)
        people_trapped = bool(_TRAPPED_PATTERN.search(text)) or None
        medical_support_required = (
            any(word in text for word in _MEDICAL_SIGNALS) or None
        )
        immediate_rescue_required = (
            any(word in text for word in _RESCUE_SIGNALS) or None
        )

        # A model does not get to assert "people are trapped" while also
        # implying zero people are affected; the validator rejects that
        # combination outright, so resolve it here rather than emit a proposal
        # the validator will only discard.
        if people_trapped and people_affected == 0:
            people_affected = None

        reasoning_factors = [*type_reasons, *severity_reasons]
        processing_ms = int((time.perf_counter() - started) * 1000)

        return AnalysisResult(
            incident_type=incident_type,
            type_confidence=type_confidence,
            severity=severity,
            severity_confidence=severity_confidence,
            people_affected=people_affected,
            people_trapped=people_trapped,
            medical_support_required=medical_support_required,
            immediate_rescue_required=immediate_rescue_required,
            entities={},
            observations=[],
            reasoning_factors=reasoning_factors,
            model_name=self.name,
            model_version=self.version,
            provider=PROVIDER,
            processing_ms=processing_ms,
        )
