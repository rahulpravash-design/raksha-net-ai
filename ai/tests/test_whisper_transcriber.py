"""Voice-report transcription (``ai/speech/whisper_transcriber.py``), against a fake client.

No network and no API key: the fake records the request it was given and returns the
response a test chooses, so what is checked is exactly what would be sent and how every
kind of answer and failure is handled.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

from ai.common.interfaces import (
    NoSpeechRecognised,
    NullTranscriber,
    SpeechConfig,
    TranscriptionUnavailable,
    get_transcriber,
)
from ai.speech.whisper_transcriber import (
    DEFAULT_MODEL,
    OPENAI_BASE_URL,
    WhisperTranscriber,
)

AUDIO = b"\x1aE\xdf\xa3" + b"webm-body"


def segment(
    text: str,
    start: float,
    end: float,
    avg_logprob: float = -0.1,
    no_speech_prob: float = 0.01,
) -> Any:
    return SimpleNamespace(
        text=text,
        start=start,
        end=end,
        avg_logprob=avg_logprob,
        no_speech_prob=no_speech_prob,
    )


def answer(*segments: Any, language: str = "english", duration: float = 6.0) -> Any:
    return SimpleNamespace(
        text=" ".join(s.text for s in segments),
        language=language,
        duration=duration,
        segments=list(segments),
    )


class FakeClient:
    """Stands in for ``openai.OpenAI``: ``client.audio.transcriptions.create(**request)``."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self._response = response
        self._error = error
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._response


def transcriber(client: FakeClient, **kwargs: Any) -> WhisperTranscriber:
    return WhisperTranscriber(api_key="sk-test", client=client, **kwargs)


# --- what is sent ----------------------------------------------------------------------
def test_the_recording_is_sent_once_with_a_generated_name_and_its_type() -> None:
    client = FakeClient(answer(segment("Water is rising.", 0, 2)))
    transcriber(client).transcribe(AUDIO, media_type="audio/webm")

    (request,) = client.requests
    assert request["file"] == ("recording.webm", AUDIO, "audio/webm")
    assert request["model"] == DEFAULT_MODEL == "whisper-1"
    # Segment detail is what the confidence is computed from.
    assert request["response_format"] == "verbose_json"
    assert request["temperature"] == 0
    assert "language" not in request  # unset: the model detects it


def test_a_language_hint_is_passed_through() -> None:
    client = FakeClient(answer(segment("தண்ணீர் உயர்கிறது", 0, 2), language="tamil"))
    result = transcriber(client).transcribe(AUDIO, media_type="audio/ogg", language="ta")

    assert client.requests[0]["language"] == "ta"
    assert client.requests[0]["file"][0] == "recording.ogg"
    assert result.language == "tamil"


def test_an_unknown_format_is_refused_before_anything_is_sent() -> None:
    client = FakeClient(answer(segment("x", 0, 1)))
    with pytest.raises(TranscriptionUnavailable, match="format"):
        transcriber(client).transcribe(AUDIO, media_type="audio/wav")
    assert client.requests == []


def test_the_base_url_is_always_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stray OPENAI_BASE_URL in the host environment must not redirect recordings."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://somewhere-else.invalid/v1")

    default = WhisperTranscriber(api_key="sk-test")
    assert str(default._client.base_url).rstrip("/") == OPENAI_BASE_URL  # type: ignore[attr-defined]
    assert default.provider == "openai"

    compatible = WhisperTranscriber(
        api_key="sk-test", base_url="https://asr.internal.example/v1"
    )
    assert str(compatible._client.base_url).startswith("https://asr.internal.example/v1")  # type: ignore[attr-defined]
    assert compatible.provider == "openai-compatible"


# --- what comes back ---------------------------------------------------------------------
def test_a_transcript_records_its_model_and_a_confidence() -> None:
    client = FakeClient(
        answer(
            segment("Five people are trapped.", 0.0, 3.0, avg_logprob=-0.1),
            segment("The water is rising.", 3.0, 4.0, avg_logprob=-0.5),
        )
    )
    result = transcriber(client).transcribe(AUDIO, media_type="audio/webm")

    assert result.text == "Five people are trapped. The water is rising."
    expected = (3.0 * math.exp(-0.1) + 1.0 * math.exp(-0.5)) / 4.0
    assert result.confidence == pytest.approx(expected, abs=1e-3)
    assert result.model_name == "whisper-1"
    assert result.model_version == WhisperTranscriber.version
    assert result.provider == "openai"
    assert result.duration_seconds == 6.0
    assert result.processing_ms >= 0


def test_noise_the_model_filled_with_words_is_dropped() -> None:
    """Whisper's own silence rule: probably-not-speech and unsure of its words."""
    client = FakeClient(
        answer(
            segment("Help, the bridge is down.", 0, 2),
            segment(
                "Thank you for watching.", 2, 5, avg_logprob=-1.4, no_speech_prob=0.9
            ),
        )
    )
    result = transcriber(client).transcribe(AUDIO, media_type="audio/webm")
    assert result.text == "Help, the bridge is down."


@pytest.mark.parametrize(
    "response",
    [
        answer(),  # nothing at all
        SimpleNamespace(text="   ", segments=[]),
        answer(segment("Thank you.", 0, 2, avg_logprob=-1.2, no_speech_prob=0.95)),
    ],
)
def test_silence_is_no_speech_not_an_empty_report(response: Any) -> None:
    with pytest.raises(NoSpeechRecognised):
        transcriber(FakeClient(response)).transcribe(AUDIO, media_type="audio/webm")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        # Words but no segments: there is nothing to compute a confidence from.
        (SimpleNamespace(text="Fire on the third floor.", segments=None), "no detail"),
        (
            SimpleNamespace(text="Fire.", segments=[SimpleNamespace(text="Fire.")]),
            "not usable",
        ),
        (answer(segment("Fire.", 0, 1, no_speech_prob=3.0)), "not usable"),
        (answer(segment("Fire.", 0, 1, avg_logprob=float("nan"))), "not usable"),
    ],
)
def test_an_unusable_answer_is_unavailable(response: Any, message: str) -> None:
    with pytest.raises(TranscriptionUnavailable, match=message):
        transcriber(FakeClient(response)).transcribe(AUDIO, media_type="audio/webm")


REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/audio/transcriptions")


def status_error(cls: type[openai.APIStatusError], code: int) -> Exception:
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=None)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (status_error(openai.AuthenticationError, 401), "API key"),
        (status_error(openai.PermissionDeniedError, 403), "may not use"),
        (status_error(openai.RateLimitError, 429), "rate-limiting"),
        (status_error(openai.BadRequestError, 400), "could not read"),
        (status_error(openai.InternalServerError, 500), "error \\(500\\)"),
        (openai.APITimeoutError(request=REQUEST), "could not be reached"),
        (openai.APIConnectionError(request=REQUEST), "could not be reached"),
    ],
)
def test_provider_failures_become_a_plain_reason(error: Exception, message: str) -> None:
    with pytest.raises(TranscriptionUnavailable, match=message):
        transcriber(FakeClient(error=error)).transcribe(AUDIO, media_type="audio/webm")


# --- selection -----------------------------------------------------------------------------
def test_without_configuration_the_null_transcriber_declines() -> None:
    assert isinstance(get_transcriber(False), NullTranscriber)
    assert isinstance(get_transcriber(True), NullTranscriber)
    # Configured but AI switched off: still nothing leaves the platform.
    assert isinstance(
        get_transcriber(False, SpeechConfig(provider="openai", api_key="k")),
        NullTranscriber,
    )
    with pytest.raises(TranscriptionUnavailable, match="type your report"):
        NullTranscriber().transcribe(AUDIO, media_type="audio/webm")


def test_get_transcriber_builds_the_configured_provider() -> None:
    configured = get_transcriber(
        True, SpeechConfig(provider="openai", api_key="sk-test", model="whisper-large-v3")
    )
    assert isinstance(configured, WhisperTranscriber)
    assert configured.model == "whisper-large-v3"
    with pytest.raises(ValueError, match="Unknown speech provider"):
        get_transcriber(True, SpeechConfig(provider="other", api_key="k"))
