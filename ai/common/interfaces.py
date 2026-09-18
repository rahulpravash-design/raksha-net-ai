"""The one interface the backend uses to reach AI.

`docs/ARCHITECTURE.md` section 9: the platform must run, and its tests must
pass, with AI entirely absent. :class:`NullAnalyzer` is what makes that true in
practice rather than only on paper.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai.common.schemas import AnalysisRequest, AnalysisResult


class AnalyzerUnavailable(RuntimeError):
    """The analyzer could not produce a result.

    Callers treat this as "no analysis", never as "nothing is wrong". Reporting
    and triage continue on the reporter's own words.
    """


@runtime_checkable
class EmergencyAnalyzer(Protocol):
    """Extracts structured information from a report. Proposes; never decides."""

    name: str
    version: str

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Return structured output, or raise :class:`AnalyzerUnavailable`."""
        ...


class NullAnalyzer:
    """The V1 analyzer: it declines, loudly and predictably.

    This is not a stub awaiting completion — it is the configured behaviour
    while `RAKSHA_AI_ENABLED` is false, and it exercises the same failure path
    the real analyzers use when a provider is down.
    """

    name = "null-analyzer"
    version = "1.0.0"

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        raise AnalyzerUnavailable(
            "AI analysis is not enabled for this deployment. "
            "The incident is triaged from the reporter's own words."
        )


def get_analyzer(enabled: bool) -> EmergencyAnalyzer:
    """Return the configured analyzer.

    Phase 6 adds the real implementations behind this function; nothing outside
    `ai/` changes when it does.
    """
    if not enabled:
        return NullAnalyzer()
    raise NotImplementedError(
        "No analyzer is implemented yet. See docs/ROADMAP.md, Phase 6."
    )
