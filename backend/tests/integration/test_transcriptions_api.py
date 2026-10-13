"""Voice reports (Phase 9): dictation, its record, and the report it is dictated into.

The speech provider is replaced by a recording fake at ``get_transcriber``, so what is
checked is what the platform would send, store and show. Three things are under test
throughout: the recording is never stored (only the transcript is), the transcript is
labelled AI-derived and kept apart from the report, and filing a report never depends
on a transcript (CLAUDE.md section 2, rules 2, 3 and 7).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from ai.common.interfaces import NoSpeechRecognised, TranscriptionUnavailable
from ai.common.schemas import Transcript
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import UserRole
from app.models.incident import AuditLog
from app.models.transcript import VoiceTranscript
from app.utils.time import utcnow

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
OGG = b"OggS" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 64

HEARD = "Five people are trapped inside a house and water is rising fast."


class FakeTranscriber:
    """Records each call; answers with a fixed transcript or raises a chosen error."""

    name, version, provider, model = "fake-whisper", "1.0.0", "openai", "whisper-1"

    def __init__(self, text: str = HEARD, error: Exception | None = None) -> None:
        self.calls: list[tuple[bytes, str, str | None]] = []
        self.text = text
        self.error = error

    def transcribe(
        self, audio: bytes, *, media_type: str, language: str | None = None
    ) -> Transcript:
        self.calls.append((audio, media_type, language))
        if self.error is not None:
            raise self.error
        return Transcript(
            text=self.text,
            confidence=0.82,
            language="english",
            duration_seconds=4.5,
            model_name="whisper-1",
            model_version="1.0.0",
            provider="openai",
            processing_ms=12,
        )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeTranscriber:
    """A fake provider, installed whether or not a provider is configured."""
    from app.services import transcription_service

    transcriber = FakeTranscriber()
    monkeypatch.setattr(
        transcription_service, "get_transcriber", lambda enabled, speech=None: transcriber
    )
    return transcriber


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch, fake: FakeTranscriber) -> FakeTranscriber:
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "speech_provider", "openai")
    monkeypatch.setattr(settings, "speech_api_key", SecretStr("sk-test"))
    return fake


def dictate(
    client: TestClient,
    audio: bytes = WEBM,
    content_type: str = "audio/webm",
    **form: str,
):
    return client.post(
        "/api/v1/transcriptions",
        files={"file": ("ignored-name.webm", audio, content_type)},
        data=form,
    )


def audit_rows(db_session: Session, action: str) -> list[AuditLog]:
    return list(
        db_session.scalars(select(AuditLog).where(AuditLog.action == action)).all()
    )


# --- availability ------------------------------------------------------------------------
def test_dictation_is_not_offered_until_a_provider_is_configured(
    as_role, monkeypatch
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    body = client.get("/api/v1/transcriptions/availability").json()
    assert body["available"] is False
    assert body["accepted_types"] == ["audio/webm", "audio/ogg", "audio/mp4"]
    assert body["languages"] == ["en", "ta"]

    # A provider without AI switched on is still off.
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_provider", "openai")
    monkeypatch.setattr(settings, "speech_api_key", SecretStr("sk-test"))
    assert client.get("/api/v1/transcriptions/availability").json()["available"] is False

    monkeypatch.setattr(settings, "ai_enabled", True)
    assert client.get("/api/v1/transcriptions/availability").json()["available"] is True


def test_availability_needs_a_signed_in_user(client: TestClient) -> None:
    assert client.get("/api/v1/transcriptions/availability").status_code == 401


# --- transcribing ------------------------------------------------------------------------
def test_unconfigured_nothing_is_read_or_sent(
    as_role, fake: FakeTranscriber, db_session: Session
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = dictate(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TRANSCRIPTION_UNAVAILABLE"
    assert "type your report" in response.json()["error"]["message"]
    assert fake.calls == []
    assert audit_rows(db_session, "ai.transcription_unavailable") == []


def test_a_recording_is_transcribed_labelled_and_not_stored(
    as_role, configured: FakeTranscriber, db_session: Session, tmp_path
) -> None:
    client, user = as_role(UserRole.CITIZEN)
    response = dictate(client, language="ta")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "AI_TRANSCRIPT"
    assert body["text"] == HEARD
    assert body["confidence"] == 0.82
    assert body["model_name"] == "whisper-1"
    assert body["model_version"] == "1.0.0"
    assert body["provider"] == "openai"
    assert body["language_hint"] == "ta"
    assert body["incident_id"] is None
    assert body["reporter_edited"] is None

    # Exactly the recording, its sniffed type and the hint went to the provider.
    assert configured.calls == [(WEBM, "audio/webm", "ta")]

    row = db_session.get(VoiceTranscript, uuid.UUID(body["id"]))
    assert row is not None and row.reporter_id == user.id
    assert row.audio_size_bytes == len(WEBM)
    assert row.audio_content_type == "audio/webm"
    # The recording was never written: nothing at all is in media storage.
    assert [f for f in (tmp_path / "media").rglob("*") if f.is_file()] == []

    (audit,) = audit_rows(db_session, "ai.transcription_created")
    assert audit.event_metadata["provider"] == "openai"
    assert audit.event_metadata["audio_size_bytes"] == len(WEBM)
    # A record of the transfer, not a second copy of the reporter's words.
    assert HEARD not in str(audit.event_metadata)


@pytest.mark.parametrize(
    ("audio", "declared", "sniffed"),
    [
        (WEBM, "audio/webm;codecs=opus", "audio/webm"),
        (OGG, "audio/ogg; codecs=opus", "audio/ogg"),
        (MP4, "audio/mp4", "audio/mp4"),
    ],
)
def test_each_browser_recording_format_is_accepted(
    as_role, configured: FakeTranscriber, audio: bytes, declared: str, sniffed: str
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    assert dictate(client, audio, declared).status_code == 201
    assert configured.calls[-1][1] == sniffed


@pytest.mark.parametrize(
    ("audio", "declared", "status", "code"),
    [
        (b"", "audio/webm", 400, "VALIDATION_ERROR"),
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "audio/wav", 415, "MEDIA_UNSUPPORTED_TYPE"),
        (WEBM, "audio/ogg", 415, "MEDIA_UNSUPPORTED_TYPE"),  # disguised
        (b"<script>alert(1)</script>", "audio/webm", 415, "MEDIA_UNSUPPORTED_TYPE"),
    ],
)
def test_a_bad_recording_is_refused_before_it_is_sent(
    as_role,
    configured: FakeTranscriber,
    audio: bytes,
    declared: str,
    status: int,
    code: str,
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = dictate(client, audio, declared)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert configured.calls == []


def test_an_oversized_recording_is_refused_before_it_is_sent(
    as_role, configured: FakeTranscriber, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "speech_max_bytes", 32)
    client, _ = as_role(UserRole.CITIZEN)
    response = dictate(client)
    assert response.status_code == 413
    assert configured.calls == []


def test_an_unknown_language_is_refused(as_role, configured: FakeTranscriber) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    response = dictate(client, language="fr")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert configured.calls == []


def test_dictation_needs_a_signed_in_user(
    client: TestClient, configured: FakeTranscriber
) -> None:
    assert dictate(client).status_code == 401
    assert configured.calls == []


def test_silence_is_reported_as_no_speech(
    as_role, configured: FakeTranscriber, db_session: Session
) -> None:
    configured.error = NoSpeechRecognised("No speech was recognised in the recording.")
    client, _ = as_role(UserRole.CITIZEN)
    response = dictate(client)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_SPEECH_RECOGNISED"
    assert db_session.scalars(select(VoiceTranscript)).all() == []
    # The recording still reached the provider, so the transfer is recorded.
    (audit,) = audit_rows(db_session, "ai.transcription_unavailable")
    assert audit.event_metadata["audio_size_bytes"] == len(WEBM)


def test_a_provider_failure_tells_the_reporter_to_type_and_operators_why(
    as_role, configured: FakeTranscriber, db_session: Session
) -> None:
    configured.error = TranscriptionUnavailable(
        "The speech provider rejected the API key."
    )
    client, _ = as_role(UserRole.CITIZEN)
    response = dictate(client)

    assert response.status_code == 503
    message = response.json()["error"]["message"]
    assert "type your report" in message
    assert "API key" not in message  # provider detail is not the reporter's concern
    (audit,) = audit_rows(db_session, "ai.transcription_unavailable")
    assert audit.event_metadata["reason"] == "The speech provider rejected the API key."


def test_dictation_rate_limit_leaves_typing_open(
    as_role, configured: FakeTranscriber, monkeypatch, incident_payload
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setattr(get_settings(), "rate_limit_transcription_per_minute", 2)
    client, _ = as_role(UserRole.CITIZEN)
    assert dictate(client).status_code == 201
    assert dictate(client).status_code == 201
    limited = dictate(client)
    assert limited.status_code == 429
    assert "type your report" in limited.json()["error"]["message"]
    # The report itself is limited separately, and still goes through.
    assert client.post("/api/v1/incidents", json=incident_payload).status_code == 201


# --- the report it was dictated into ----------------------------------------------------
def test_a_dictated_report_links_its_transcript(
    as_role, configured: FakeTranscriber, incident_payload, db_session: Session
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    transcript = dictate(client).json()

    payload = incident_payload | {"description": HEARD, "transcript_id": transcript["id"]}
    incident = client.post("/api/v1/incidents", json=payload)
    assert incident.status_code == 201, incident.text
    assert incident.json()["description"] == HEARD

    row = db_session.get(VoiceTranscript, uuid.UUID(transcript["id"]))
    assert row is not None
    db_session.refresh(row)
    assert str(row.incident_id) == incident.json()["id"]
    assert row.reporter_edited is False
    assert row.linked_at is not None

    created = audit_rows(db_session, "incident.created")[-1]
    assert created.event_metadata["dictated"] is True


def test_a_corrected_transcript_is_marked_as_edited(
    as_role, configured: FakeTranscriber, incident_payload, db_session: Session
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    transcript = dictate(client).json()
    corrected = "Six people are trapped inside a house and water is rising fast."
    payload = incident_payload | {
        "description": corrected,
        "transcript_id": transcript["id"],
    }
    assert client.post("/api/v1/incidents", json=payload).status_code == 201

    row = db_session.get(VoiceTranscript, uuid.UUID(transcript["id"]))
    assert row is not None
    db_session.refresh(row)
    assert row.reporter_edited is True
    assert row.text == HEARD  # what the model heard is kept as it heard it


def test_someone_elses_transcript_is_not_attached_but_the_report_is_filed(
    authed_client,
    make_user,
    configured: FakeTranscriber,
    incident_payload,
    db_session: Session,
) -> None:
    owner, other = make_user(UserRole.CITIZEN), make_user(UserRole.CITIZEN)
    transcript = dictate(authed_client(owner)).json()

    client = authed_client(other)
    payload = incident_payload | {"transcript_id": transcript["id"]}
    response = client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201  # rule 7: the report never waits on AI

    row = db_session.get(VoiceTranscript, uuid.UUID(transcript["id"]))
    assert row is not None
    db_session.refresh(row)
    assert row.incident_id is None
    assert (
        audit_rows(db_session, "incident.created")[-1].event_metadata["dictated"] is False
    )


def test_a_transcript_belongs_to_one_report_only(
    as_role, configured: FakeTranscriber, incident_payload, db_session: Session
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    transcript = dictate(client).json()
    payload = incident_payload | {"transcript_id": transcript["id"]}
    first = client.post("/api/v1/incidents", json=payload).json()
    second = client.post("/api/v1/incidents", json=payload)
    assert second.status_code == 201

    row = db_session.get(VoiceTranscript, uuid.UUID(transcript["id"]))
    assert row is not None
    db_session.refresh(row)
    assert str(row.incident_id) == first["id"]


def test_an_unknown_transcript_id_does_not_stop_a_report(
    as_role, incident_payload
) -> None:
    client, _ = as_role(UserRole.CITIZEN)
    payload = incident_payload | {"transcript_id": str(uuid.uuid4())}
    assert client.post("/api/v1/incidents", json=payload).status_code == 201


def test_stale_unsent_transcripts_are_cleared_when_anyone_next_dictates(
    authed_client, make_user, configured: FakeTranscriber, db_session: Session
) -> None:
    """Opportunistic, not scheduled: there is no job runner yet (DATABASE.md section 6)."""
    reporter, someone_else = make_user(UserRole.CITIZEN), make_user(UserRole.CITIZEN)

    def unsent(owner_id: uuid.UUID, age: timedelta) -> VoiceTranscript:
        row = VoiceTranscript(
            reporter_id=owner_id,
            text="old words",
            confidence=0.5,
            model_name="whisper-1",
            model_version="1.0.0",
            provider="openai",
            processing_ms=1,
            audio_content_type="audio/webm",
            audio_size_bytes=10,
        )
        db_session.add(row)
        db_session.flush()
        row.created_at = utcnow() - age
        db_session.commit()
        return row

    old_ids = [
        unsent(reporter.id, timedelta(days=2)).id,
        unsent(someone_else.id, timedelta(days=2)).id,
    ]
    recent_id = unsent(someone_else.id, timedelta(hours=1)).id

    # Anyone dictating clears out what has expired, whoever it belonged to.
    fresh = dictate(authed_client(reporter))
    assert fresh.status_code == 201
    db_session.expire_all()

    assert [db_session.get(VoiceTranscript, i) for i in old_ids] == [None, None]
    assert db_session.get(VoiceTranscript, recent_id) is not None  # still inside its day
    assert db_session.get(VoiceTranscript, uuid.UUID(fresh.json()["id"])) is not None


# --- what operators see -----------------------------------------------------------------
def dictated_incident(authed_client, make_user, incident_payload) -> tuple[str, str]:
    reporter = make_user(UserRole.CITIZEN)
    client = authed_client(reporter)
    transcript = dictate(client).json()
    payload = incident_payload | {"description": HEARD, "transcript_id": transcript["id"]}
    return client.post("/api/v1/incidents", json=payload).json()["id"], transcript["id"]


def test_a_dispatcher_sees_the_transcript_labelled_as_ai(
    authed_client, make_user, configured: FakeTranscriber, incident_payload
) -> None:
    incident_id, transcript_id = dictated_incident(
        authed_client, make_user, incident_payload
    )
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))

    response = dispatcher.get(f"/api/v1/incidents/{incident_id}/transcripts")
    assert response.status_code == 200
    (row,) = response.json()
    assert row["id"] == transcript_id
    assert row["source"] == "AI_TRANSCRIPT"
    assert row["model_name"] == "whisper-1"
    assert row["confidence"] == 0.82
    assert row["reporter_edited"] is False


@pytest.mark.parametrize(
    "role", [UserRole.CITIZEN, UserRole.RESPONDER, UserRole.HOSPITAL_OPERATOR]
)
def test_other_roles_cannot_list_transcripts(
    authed_client, make_user, configured: FakeTranscriber, incident_payload, role
) -> None:
    incident_id, _ = dictated_incident(authed_client, make_user, incident_payload)
    client = authed_client(make_user(role))
    assert client.get(f"/api/v1/incidents/{incident_id}/transcripts").status_code == 403


def test_the_reporter_cannot_list_transcripts_either(
    authed_client, make_user, configured: FakeTranscriber, incident_payload
) -> None:
    """The reporter already has their own words; the AI record is for operators."""
    reporter = make_user(UserRole.CITIZEN)
    client = authed_client(reporter)
    transcript = dictate(client).json()
    payload = incident_payload | {"transcript_id": transcript["id"]}
    incident_id = client.post("/api/v1/incidents", json=payload).json()["id"]
    assert client.get(f"/api/v1/incidents/{incident_id}/transcripts").status_code == 403


def test_listing_transcripts_needs_a_signed_in_user_and_a_real_incident(
    client: TestClient, authed_client, make_user
) -> None:
    path = f"/api/v1/incidents/{uuid.uuid4()}/transcripts"
    assert client.get(path).status_code == 401
    dispatcher = authed_client(make_user(UserRole.DISPATCHER))
    assert dispatcher.get(path).status_code == 404
