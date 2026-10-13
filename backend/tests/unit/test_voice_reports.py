"""Voice reports: recognising a recording, and the speech settings a deployment may use."""

from __future__ import annotations

import pytest

from app.core.config import Settings, generate_encryption_key
from app.utils.audio import ACCEPTED_AUDIO_TYPES, sniff_audio_type


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81", "audio/webm"),  # Chrome, Edge, Firefox
        (b"OggS\x00\x02\x00\x00", "audio/ogg"),  # Firefox
        (b"\x00\x00\x00\x1cftypM4A \x00\x00\x00\x00", "audio/mp4"),  # Safari
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", None),  # WAV: browsers do not record it
        (b"ID3\x04\x00\x00\x00\x00", None),  # MP3
        (b"\xff\xd8\xff\xe0", None),  # a JPEG passed off as audio
        (b"ftyp", None),  # too short to be an MP4 box
        (b"", None),
    ],
)
def test_recordings_are_recognised_by_their_own_bytes(
    content: bytes, expected: str | None
) -> None:
    assert sniff_audio_type(content) == expected


def test_every_accepted_type_can_be_recognised() -> None:
    samples = {
        "audio/webm": b"\x1a\x45\xdf\xa3",
        "audio/ogg": b"OggS",
        "audio/mp4": b"\x00\x00\x00\x18ftypmp42",
    }
    assert {sniff_audio_type(samples[t]) for t in ACCEPTED_AUDIO_TYPES} == set(
        ACCEPTED_AUDIO_TYPES
    )


def _production(**overrides: object) -> Settings:
    return Settings(
        environment="production",
        debug=False,
        secret_key="a-production-grade-secret-key-0123456789",
        cors_origins=["https://app.example.org"],
        mfa_required_for_operational=True,
        encryption_key=generate_encryption_key(),
        **overrides,  # type: ignore[arg-type]
    )


def test_speech_is_off_by_default() -> None:
    settings = Settings()
    assert settings.speech_provider is None
    assert settings.speech_api_key is None


def test_production_refuses_to_send_recordings_in_clear() -> None:
    with pytest.raises(RuntimeError, match="RAKSHA_SPEECH_BASE_URL must be an https"):
        _production(
            speech_provider="openai",
            speech_api_key="sk-test",
            speech_base_url="http://asr.internal:8000/v1",
        ).assert_safe_for_environment()


def test_production_accepts_an_https_compatible_service() -> None:
    _production(
        speech_provider="openai",
        speech_api_key="sk-test",
        speech_base_url="https://asr.internal.example/v1",
    ).assert_safe_for_environment()


def test_the_size_cap_cannot_exceed_what_the_provider_accepts() -> None:
    with pytest.raises(ValueError):
        Settings(speech_max_bytes=26 * 1024 * 1024)
