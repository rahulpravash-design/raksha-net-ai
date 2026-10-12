"""Photo observations by Claude (``ai/vision/claude_observer.py``), against a fake client.

No network and no API key: the fake records the request it was given and returns the
response a test chooses, so what is checked is exactly what would be sent and how every
kind of answer, refusal and failure is handled.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from ai.common.composite import CompositeAnalyzer
from ai.common.interfaces import (
    MAX_IMAGES,
    ObservationUnavailable,
    VisionConfig,
    get_analyzer,
)
from ai.common.schemas import OBSERVATION_VOCABULARY, AnalysisRequest, AnalysisSource
from ai.common.validation import validate_analysis
from ai.nlp.text_analyzer import HeuristicTextAnalyzer
from ai.vision.claude_observer import (
    DEFAULT_MODEL,
    ClaudeImageObserver,
    sniff_image_type,
)

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"webp-body"


def answer(observations: list[dict[str, Any]], stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="text", text=json.dumps({"observations": observations}))
        ],
    )


class FakeClient:
    """Stands in for ``anthropic.Anthropic``: ``client.beta.messages.create(**request)``."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self._response = response
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._response


def observer(client: FakeClient, model: str | None = None) -> ClaudeImageObserver:
    return ClaudeImageObserver(api_key="sk-test", model=model, client=client)


# --- what is sent ----------------------------------------------------------------------
def test_photos_are_sent_base64_with_their_sniffed_type() -> None:
    client = FakeClient(answer([]))
    observer(client).observe([JPEG, PNG, WEBP])

    content = client.requests[0]["messages"][0]["content"]
    images = [block for block in content if block["type"] == "image"]
    assert [i["source"]["media_type"] for i in images] == [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
    assert base64.standard_b64decode(images[0]["source"]["data"]) == JPEG
    assert content[-1]["type"] == "text"


def test_at_most_four_photos_are_sent() -> None:
    client = FakeClient(answer([]))
    observer(client).observe([JPEG] * 9)
    content = client.requests[0]["messages"][0]["content"]
    assert sum(block["type"] == "image" for block in content) == MAX_IMAGES == 4


def test_an_unrecognised_file_is_not_sent_and_none_at_all_is_unavailable() -> None:
    client = FakeClient(answer([]))
    observer(client).observe([b"not an image", JPEG])
    assert (
        sum(b["type"] == "image" for b in client.requests[0]["messages"][0]["content"])
        == 1
    )

    with pytest.raises(ObservationUnavailable, match="format"):
        observer(FakeClient(answer([]))).observe([b"not an image"])


def test_the_answer_is_constrained_to_the_vocabulary_by_schema() -> None:
    client = FakeClient(answer([]))
    observer(client).observe([JPEG])

    request = client.requests[0]
    output_format = request["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    item = output_format["schema"]["properties"]["observations"]["items"]
    assert set(item["properties"]["label"]["enum"]) == OBSERVATION_VOCABULARY
    assert item["additionalProperties"] is False
    assert request["output_config"]["effort"] == "medium"


def test_the_default_model_has_refusal_fallbacks_on() -> None:
    client = FakeClient(answer([]))
    observer(client).observe([JPEG])

    request = client.requests[0]
    assert request["model"] == DEFAULT_MODEL == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert request["betas"] == ["server-side-fallback-2026-07-01"]


def test_a_model_without_server_side_fallbacks_is_sent_without_them() -> None:
    client = FakeClient(answer([]))
    observer(client, model="claude-haiku-5-5").observe([JPEG])
    assert "fallbacks" not in client.requests[0]
    assert "betas" not in client.requests[0]


def test_the_reporters_words_and_ids_are_not_sent_with_the_photos() -> None:
    """Only the photographs and fixed instructions leave the platform."""
    client = FakeClient(answer([]))
    request = AnalysisRequest(
        incident_id="incident-7f3a",
        description="Asha at 14 Gandhi Street says the kitchen is on fire",
        image_bytes=[JPEG],
    )
    CompositeAnalyzer(HeuristicTextAnalyzer(), observer(client)).analyze(request)

    sent = json.dumps(client.requests[0], default=str)
    for private in ("Asha", "Gandhi Street", "incident-7f3a", "kitchen"):
        assert private not in sent


# --- what comes back ---------------------------------------------------------------------
def test_observations_become_image_observations_strongest_first() -> None:
    client = FakeClient(
        answer(
            [
                {"label": "smoke_visible", "confidence": 0.4},
                {"label": "flames_visible", "confidence": 0.9},
                {
                    "label": "smoke_visible",
                    "confidence": 0.7,
                },  # repeated: keep the higher
            ]
        )
    )
    result = observer(client).observe([JPEG])

    assert [(o.label, o.confidence) for o in result] == [
        ("flames_visible", 0.9),
        ("smoke_visible", 0.7),
    ]
    assert all(o.source is AnalysisSource.IMAGE for o in result)


def test_an_empty_answer_is_a_valid_answer() -> None:
    assert observer(FakeClient(answer([]))).observe([JPEG]) == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (answer([], stop_reason="refusal"), "declined"),
        (answer([], stop_reason="max_tokens"), "cut short"),
        (SimpleNamespace(stop_reason="end_turn", content=[]), "no answer"),
        (
            SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text="{oops")],
            ),
            "not usable",
        ),
        (answer([{"label": "injured_person", "confidence": 0.9}]), "not usable"),
        (answer([{"label": "smoke_visible", "confidence": 1.7}]), "not usable"),
        (answer([{"label": "smoke_visible"}]), "not usable"),
    ],
)
def test_an_unusable_or_refused_answer_is_unavailable_not_empty(
    response: Any, message: str
) -> None:
    """ "No answer" must never read as "nothing visible"."""
    with pytest.raises(ObservationUnavailable, match=message):
        observer(FakeClient(response)).observe([JPEG])


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls: type[anthropic.APIStatusError], code: int) -> Exception:
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=None)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (status_error(anthropic.AuthenticationError, 401), "API key"),
        (status_error(anthropic.PermissionDeniedError, 403), "may not use"),
        (status_error(anthropic.RateLimitError, 429), "rate-limiting"),
        (status_error(anthropic.BadRequestError, 400), "rejected the request"),
        (status_error(anthropic.InternalServerError, 500), "error \\(500\\)"),
        (anthropic.APITimeoutError(request=REQUEST), "could not be reached"),
        (anthropic.APIConnectionError(request=REQUEST), "could not be reached"),
    ],
)
def test_provider_failures_become_a_plain_reason(error: Exception, message: str) -> None:
    with pytest.raises(ObservationUnavailable, match=message):
        observer(FakeClient(error=error)).observe([JPEG])


def test_sniffing_knows_the_formats_and_nothing_else() -> None:
    assert sniff_image_type(JPEG) == "image/jpeg"
    assert sniff_image_type(PNG) == "image/png"
    assert sniff_image_type(WEBP) == "image/webp"
    assert sniff_image_type(b"GIF89a....") == "image/gif"
    assert sniff_image_type(b"RIFF\x00\x00\x00\x00WAVE") is None
    assert sniff_image_type(b"") is None


# --- text plus photographs -----------------------------------------------------------------
def request_with(*images: bytes) -> AnalysisRequest:
    return AnalysisRequest(
        incident_id="i-1",
        description="Fire in the building, smoke everywhere, people trapped upstairs",
        image_bytes=list(images),
    )


def test_composite_adds_photo_observations_and_names_both_models() -> None:
    text = HeuristicTextAnalyzer()
    client = FakeClient(answer([{"label": "flames_visible", "confidence": 0.8}]))
    result = validate_analysis(
        CompositeAnalyzer(text, observer(client)).analyze(request_with(JPEG))
    )

    text_only = text.analyze(request_with())
    assert result.incident_type == text_only.incident_type  # the text proposal is intact
    assert [o.label for o in result.observations if o.source is AnalysisSource.IMAGE] == [
        "flames_visible"
    ]
    assert result.model_name == f"{text.name}+claude-opus-5-5"
    assert result.provider == "anthropic"
    assert any(
        "AI-derived and unverified" in factor for factor in result.reasoning_factors
    )


def test_composite_keeps_the_text_proposal_when_photos_fail() -> None:
    text = HeuristicTextAnalyzer()
    client = FakeClient(error=anthropic.APIConnectionError(request=REQUEST))
    result = CompositeAnalyzer(text, observer(client)).analyze(request_with(JPEG))

    assert result.model_name == text.name  # nothing claims a model that did not run
    assert not [o for o in result.observations if o.source is AnalysisSource.IMAGE]
    assert any("Photographs were not analysed" in f for f in result.reasoning_factors)


def test_composite_does_not_call_the_provider_without_photos() -> None:
    client = FakeClient(answer([]))
    CompositeAnalyzer(HeuristicTextAnalyzer(), observer(client)).analyze(request_with())
    assert client.requests == []


def test_get_analyzer_adds_photos_only_when_configured() -> None:
    assert isinstance(get_analyzer(True), HeuristicTextAnalyzer)
    configured = get_analyzer(True, VisionConfig(provider="anthropic", api_key="sk-test"))
    assert isinstance(configured, CompositeAnalyzer)
    with pytest.raises(ValueError, match="Unknown photo-analysis provider"):
        get_analyzer(True, VisionConfig(provider="other", api_key="k"))
