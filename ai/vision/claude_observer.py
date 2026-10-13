"""Observations from report photographs, by Claude (Phase 8).

What it does: sends the photographs attached to a report to Claude and asks which labels
from :data:`ai.common.schemas.OBSERVATION_VOCABULARY` are visible, each with a confidence.
The answer is constrained to that vocabulary by a JSON schema (structured output) and
then validated again here and in :func:`ai.common.validation.validate_analysis`.

What it is not: a finding. Every label is phrased as an observation ("possible injured
person"), the result is stored as AI-derived next to (never instead of) the reporter's
words, and only a person decides anything. Its accuracy on emergency photographs has not
been measured: there is no labelled photo set (``docs/ROADMAP.md``, Phase 8).

Privacy: only the image bytes leave the platform. They have already had their embedded
metadata (EXIF GPS position, device serial, thumbnails) stripped at upload
(``backend/app/utils/image_metadata.py``); no identity, contact detail or coordinate is
sent (``AnalysisRequest`` carries none).

Off unless a deployment configures it (``RAKSHA_AI_PROVIDER=anthropic`` and an API key):
this module is imported only then, so the platform runs and its tests pass without it.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Protocol

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from ai.common.interfaces import MAX_IMAGES, ObservationUnavailable
from ai.common.schemas import OBSERVATION_VOCABULARY, AnalysisSource, Observation

logger = logging.getLogger(__name__)

#: The default when ``RAKSHA_AI_MODEL`` is unset.
DEFAULT_MODEL = "claude-opus-5-5"

#: Models that take the server-side refusal fallback (``fallbacks: "default"``). For any
#: other model the parameter is left out rather than risk a 400.
_FALLBACK_MODELS = frozenset(
    {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
)
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_SYSTEM = (
    "You assist emergency dispatchers by describing what is visible in photographs "
    "attached to an emergency report. Answer only with labels from the list you are "
    "given, each with a confidence between 0 and 1 that it is visible in the "
    "photographs. Report only what the photographs themselves show, not what the "
    "situation might involve. If a label is doubtful, give it a low confidence or "
    "leave it out. An empty list is a valid answer. A person decides what to do; "
    "your answer is one input to that decision."
)

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "enum": sorted(OBSERVATION_VOCABULARY)},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["observations"],
    "additionalProperties": False,
}


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    confidence: float


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[_Item]


class MessagesClient(Protocol):
    """The part of ``anthropic.Anthropic`` this module uses (a test can supply a fake)."""

    @property
    def beta(self) -> Any: ...


def sniff_image_type(data: bytes) -> str | None:
    """The media type Claude needs, from the file's own bytes (the upload checked them)."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


class ClaudeImageObserver:
    """Turns photographs into vocabulary observations with Claude's vision."""

    name = "claude-vision"
    version = "1.0.0"
    provider = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        timeout_seconds: float = 20.0,
        client: MessagesClient | None = None,
    ) -> None:
        self.model = model or DEFAULT_MODEL
        # One retry: a dispatcher is waiting, and the text analysis does not depend on it.
        self._client: MessagesClient = client or anthropic.Anthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=1
        )

    def observe(self, images: list[bytes]) -> list[Observation]:
        blocks = self._image_blocks(images)
        if not blocks:
            raise ObservationUnavailable(
                "No photograph was in a format that can be analysed."
            )

        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "system": _SYSTEM,
            "output_config": {
                # Recognising labels in a photograph is a short classification;
                # Claude Opus 5.5 defaults to medium, set here so it is explicit.
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            "messages": [
                {
                    "role": "user",
                    "content": [
                        *blocks,
                        {
                            "type": "text",
                            "text": "Which labels are visible in these photographs?",
                        },
                    ],
                }
            ],
        }
        if self.model in _FALLBACK_MODELS:
            request["betas"] = [_FALLBACK_BETA]
            request["fallbacks"] = "default"

        try:
            response = self._client.beta.messages.create(**request)
        except anthropic.AuthenticationError as exc:
            raise ObservationUnavailable("The AI provider rejected the API key.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ObservationUnavailable("The API key may not use this model.") from exc
        except anthropic.RateLimitError as exc:
            raise ObservationUnavailable(
                "The AI provider is rate-limiting requests."
            ) from exc
        except anthropic.BadRequestError as exc:
            logger.warning("vision_request_rejected", extra={"status": exc.status_code})
            raise ObservationUnavailable("The AI provider rejected the request.") from exc
        except anthropic.APIStatusError as exc:
            raise ObservationUnavailable(
                f"The AI provider returned an error ({exc.status_code})."
            ) from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise ObservationUnavailable("The AI provider could not be reached.") from exc

        return self._parse(response)

    def _image_blocks(self, images: list[bytes]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for data in images[:MAX_IMAGES]:
            media_type = sniff_image_type(data)
            if media_type is None:
                continue
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(data).decode("ascii"),
                    },
                }
            )
        return blocks

    @staticmethod
    def _parse(response: Any) -> list[Observation]:
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            raise ObservationUnavailable(
                "The AI model declined to analyse these photographs."
            )
        if stop_reason == "max_tokens":
            raise ObservationUnavailable("The AI model's answer was cut short.")

        text = next(
            (
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ),
            None,
        )
        if text is None:
            raise ObservationUnavailable("The AI model returned no answer.")
        try:
            answer = _Answer.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ObservationUnavailable("The AI model's answer was not usable.") from exc

        best: dict[str, float] = {}
        for item in answer.observations:
            # The schema already limits labels and ranges; nothing outside is believed.
            if (
                item.label not in OBSERVATION_VOCABULARY
                or not 0.0 <= item.confidence <= 1.0
            ):
                raise ObservationUnavailable("The AI model's answer was not usable.")
            best[item.label] = max(item.confidence, best.get(item.label, 0.0))
        return [
            Observation(
                label=label,
                confidence=round(confidence, 3),
                source=AnalysisSource.IMAGE,
            )
            for label, confidence in sorted(best.items(), key=lambda pair: -pair[1])
        ]
