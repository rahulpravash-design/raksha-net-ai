"""Speech to text for voice reports, through an OpenAI-compatible transcription API (Phase 9).

What it does: sends one recording to the provider's transcription endpoint and returns the
words it heard with a confidence. The recording is held in memory only: nothing here writes
it anywhere, and the backend stores the transcript, never the audio.

What it is not: the report. The reporter reads the transcript in the report form and
corrects it before sending, and the stored transcript is labelled AI-derived next to the
report it was dictated into. Its word error rate in English, Tamil and code-mixed speech
has not been measured: there is no recorded test set (``docs/ROADMAP.md``, Phase 9).

Confidence: the duration-weighted mean, over the segments kept, of ``exp(avg_logprob)`` --
the model's own average token probability. It ranks transcripts; it is not an accuracy.

Off unless a deployment configures it (``RAKSHA_SPEECH_PROVIDER=openai`` and a key): this
module is imported only then, so the platform runs and its tests pass without it.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Protocol

import openai
from pydantic import BaseModel, ConfigDict, ValidationError

from ai.common.interfaces import NoSpeechRecognised, TranscriptionUnavailable
from ai.common.schemas import Transcript

logger = logging.getLogger(__name__)

#: The default when ``RAKSHA_SPEECH_MODEL`` is unset. A model must return segment detail
#: (``verbose_json``): the confidence every transcript records is computed from it.
DEFAULT_MODEL = "whisper-1"

#: OpenAI's own endpoint, passed explicitly: left unset, the SDK would read
#: ``OPENAI_BASE_URL`` from the environment, and a stray variable could send citizens'
#: recordings somewhere this platform's configuration never named.
OPENAI_BASE_URL = "https://api.openai.com/v1"

#: The provider infers the format from the file name, so each accepted type gets one.
_FILE_NAMES = {
    "audio/webm": "recording.webm",
    "audio/ogg": "recording.ogg",
    "audio/mp4": "recording.mp4",
}

#: Whisper's own silence rule: a segment the model rates as probably not speech, and
#: whose words it was unsure of, is noise it filled with words. It is dropped.
_NO_SPEECH_PROBABILITY = 0.6
_LOW_LOGPROB = -1.0


class _Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    start: float
    end: float
    avg_logprob: float
    no_speech_prob: float


class TranscriptionClient(Protocol):
    """The part of ``openai.OpenAI`` this module uses (a test can supply a fake)."""

    @property
    def audio(self) -> Any: ...


class WhisperTranscriber:
    """Transcribes a voice report with a Whisper model over an OpenAI-compatible API."""

    name = "whisper-transcriber"
    version = "1.0.0"

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        client: TranscriptionClient | None = None,
    ) -> None:
        self.model = model or DEFAULT_MODEL
        self.provider = "openai" if base_url is None else "openai-compatible"
        # One retry: a reporter is waiting, and can always type instead.
        self._client: TranscriptionClient = client or openai.OpenAI(
            api_key=api_key,
            base_url=base_url or OPENAI_BASE_URL,
            timeout=timeout_seconds,
            max_retries=1,
        )

    def transcribe(
        self, audio: bytes, *, media_type: str, language: str | None = None
    ) -> Transcript:
        file_name = _FILE_NAMES.get(media_type)
        if file_name is None:
            raise TranscriptionUnavailable("That recording format cannot be transcribed.")

        request: dict[str, Any] = {
            "file": (file_name, audio, media_type),
            "model": self.model,
            "response_format": "verbose_json",
            "temperature": 0,
        }
        if language:
            request["language"] = language

        started = time.perf_counter()
        try:
            response = self._client.audio.transcriptions.create(**request)
        except openai.AuthenticationError as exc:
            raise TranscriptionUnavailable(
                "The speech provider rejected the API key."
            ) from exc
        except openai.PermissionDeniedError as exc:
            raise TranscriptionUnavailable(
                "The API key may not use this speech model."
            ) from exc
        except openai.RateLimitError as exc:
            raise TranscriptionUnavailable(
                "The speech provider is rate-limiting requests."
            ) from exc
        except openai.BadRequestError as exc:
            logger.warning("speech_request_rejected", extra={"status": exc.status_code})
            raise TranscriptionUnavailable(
                "The speech provider could not read this recording."
            ) from exc
        except openai.APIStatusError as exc:
            raise TranscriptionUnavailable(
                f"The speech provider returned an error ({exc.status_code})."
            ) from exc
        except openai.APIConnectionError as exc:  # includes timeouts
            raise TranscriptionUnavailable(
                "The speech provider could not be reached."
            ) from exc
        processing_ms = int((time.perf_counter() - started) * 1000)

        return self._parse(response, processing_ms=processing_ms)

    def _parse(self, response: Any, *, processing_ms: int) -> Transcript:
        raw_segments = getattr(response, "segments", None)
        if not (getattr(response, "text", None) or "").strip():
            raise NoSpeechRecognised("No speech was recognised in the recording.")
        if not raw_segments:
            # Without segments there is no confidence, and every AI output records one.
            raise TranscriptionUnavailable(
                "The speech provider's answer had no detail to judge it by."
            )
        try:
            segments = [
                _Segment.model_validate(segment, from_attributes=True)
                for segment in raw_segments
            ]
        except ValidationError as exc:
            raise TranscriptionUnavailable(
                "The speech provider's answer was not usable."
            ) from exc
        if any(
            not (math.isfinite(s.avg_logprob) and 0.0 <= s.no_speech_prob <= 1.0)
            for s in segments
        ):
            raise TranscriptionUnavailable("The speech provider's answer was not usable.")

        heard = [
            s
            for s in segments
            if s.text.strip()
            and not (
                s.no_speech_prob > _NO_SPEECH_PROBABILITY and s.avg_logprob < _LOW_LOGPROB
            )
        ]
        if not heard:
            raise NoSpeechRecognised("No speech was recognised in the recording.")

        duration = getattr(response, "duration", None)
        language = getattr(response, "language", None)
        return Transcript(
            text=" ".join(s.text.strip() for s in heard),
            confidence=round(_confidence(heard), 3),
            language=language if isinstance(language, str) and language else None,
            duration_seconds=(
                float(duration)
                if isinstance(duration, int | float) and duration >= 0
                else None
            ),
            model_name=self.model,
            model_version=self.version,
            provider=self.provider,
            processing_ms=processing_ms,
        )


def _confidence(segments: list[_Segment]) -> float:
    """The model's average token probability, weighted by how long each segment lasts."""
    weights = [max(s.end - s.start, 0.0) for s in segments]
    probabilities = [min(math.exp(min(s.avg_logprob, 0.0)), 1.0) for s in segments]
    total = sum(weights)
    if total <= 0:
        return sum(probabilities) / len(probabilities)
    return sum(w * p for w, p in zip(weights, probabilities, strict=True)) / total
