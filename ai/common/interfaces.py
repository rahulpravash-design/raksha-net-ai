"""The one interface the backend uses to reach AI.

`docs/ARCHITECTURE.md` section 9: the platform must run, and its tests must
pass, with AI entirely absent. :class:`NullAnalyzer` is what makes that true in
practice rather than only on paper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ai.common.schemas import AnalysisRequest, AnalysisResult, Observation, Transcript


class AnalyzerUnavailable(RuntimeError):
    """The analyzer could not produce a result.

    Callers treat this as "no analysis", never as "nothing is wrong". Reporting
    and triage continue on the reporter's own words.
    """


#: Photographs per analysis, and bytes per photograph, that an image observer accepts.
#: 5 MB is the per-image limit of the provider in use (Anthropic); larger photos are
#: skipped by the backend rather than sent to fail.
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class ObservationUnavailable(RuntimeError):
    """Photographs could not be analysed. The message is safe to show a dispatcher.

    Like :class:`AnalyzerUnavailable` it means "no observations", never "nothing seen".
    """


@runtime_checkable
class ImageObserver(Protocol):
    """Proposes observations from photographs. Never decides anything."""

    name: str
    version: str
    provider: str
    model: str

    def observe(self, images: list[bytes]) -> list[Observation]:
        """Return observations, or raise :class:`ObservationUnavailable`."""
        ...


@dataclass(frozen=True)
class VisionConfig:
    """What the backend passes when a deployment has configured a photo provider."""

    provider: str
    api_key: str
    model: str | None = None
    timeout_seconds: float = 20.0


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


def get_analyzer(enabled: bool, vision: VisionConfig | None = None) -> EmergencyAnalyzer:
    """Return the configured analyzer.

    The import is local so that importing ``ai.common`` — which the backend
    does unconditionally — never pulls in the analyzer implementation. With AI
    disabled (the default), nothing beyond this module and
    :class:`NullAnalyzer` is touched, which is what keeps ``docs/ARCHITECTURE.md``
    section 9's promise true: core business logic runs and passes its tests
    with AI entirely absent.
    """
    if not enabled:
        return NullAnalyzer()
    from ai.nlp.text_analyzer import HeuristicTextAnalyzer

    text = HeuristicTextAnalyzer()
    if vision is None:
        return text
    if vision.provider != "anthropic":
        raise ValueError(f"Unknown photo-analysis provider: {vision.provider!r}")

    # Imported only when configured: without it no provider SDK is loaded at all.
    from ai.common.composite import CompositeAnalyzer
    from ai.vision.claude_observer import ClaudeImageObserver

    return CompositeAnalyzer(
        text,
        ClaudeImageObserver(
            api_key=vision.api_key,
            model=vision.model,
            timeout_seconds=vision.timeout_seconds,
        ),
    )


# --- speech (Phase 9) ----------------------------------------------------------------
class TranscriptionUnavailable(RuntimeError):
    """A recording could not be transcribed. The message is safe to show the reporter.

    It means "no transcript", never "nothing was said": the reporter types instead.
    """


class NoSpeechRecognised(TranscriptionUnavailable):
    """The provider answered, but heard no speech in the recording."""


@runtime_checkable
class Transcriber(Protocol):
    """Turns one recording into words a reporter then checks. Never decides anything."""

    name: str
    version: str
    provider: str
    model: str

    def transcribe(
        self, audio: bytes, *, media_type: str, language: str | None = None
    ) -> Transcript:
        """Return the words heard, or raise :class:`TranscriptionUnavailable`."""
        ...


@dataclass(frozen=True)
class SpeechConfig:
    """What the backend passes when a deployment has configured a speech provider."""

    provider: str
    api_key: str
    model: str | None = None
    #: An OpenAI-compatible service instead of OpenAI itself; None = the provider's own.
    base_url: str | None = None
    timeout_seconds: float = 30.0


class NullTranscriber:
    """No speech provider is configured: it declines, the same way :class:`NullAnalyzer` does."""

    name = "null-transcriber"
    version = "1.0.0"
    provider = "none"
    model = "none"

    def transcribe(
        self, audio: bytes, *, media_type: str, language: str | None = None
    ) -> Transcript:
        raise TranscriptionUnavailable(
            "Voice reports are not available on this service. Please type your report."
        )


def get_transcriber(enabled: bool, speech: SpeechConfig | None = None) -> Transcriber:
    """Return the configured transcriber; the provider SDK is imported only when used."""
    if not enabled or speech is None:
        return NullTranscriber()
    if speech.provider != "openai":
        raise ValueError(f"Unknown speech provider: {speech.provider!r}")

    from ai.speech.whisper_transcriber import WhisperTranscriber

    return WhisperTranscriber(
        api_key=speech.api_key,
        model=speech.model,
        base_url=speech.base_url,
        timeout_seconds=speech.timeout_seconds,
    )
