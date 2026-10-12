"""Voice reports (Phase 9): dictation for the report form, and its record for operators.

Deliberately not part of ``incidents.py``: a transcript is AI output, kept apart from
the report it was dictated into (CLAUDE.md section 2, rule 2).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from ai.common.schemas import SPEECH_LANGUAGE_HINTS
from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.deps import AppSettings, Context, CurrentUser, DbSession, IncidentViewer
from app.core.errors import MediaTooLargeError, RateLimitedError
from app.core.rate_limit import get_rate_limiter
from app.schemas.transcript import TranscriptionAvailability, VoiceTranscriptRead
from app.services.transcription_service import TranscriptionService, UploadedAudio
from app.utils.audio import ACCEPTED_AUDIO_TYPES

router = APIRouter(tags=["voice-reports"])


@router.get(
    "/transcriptions/availability",
    response_model=TranscriptionAvailability,
    summary="Whether the report form may offer dictation",
)
def transcription_availability(
    user: CurrentUser, session: DbSession, settings: AppSettings
) -> TranscriptionAvailability:
    return TranscriptionAvailability(
        available=TranscriptionService(session, settings).is_available(),
        max_bytes=settings.speech_max_bytes,
        accepted_types=list(ACCEPTED_AUDIO_TYPES),
        languages=sorted(SPEECH_LANGUAGE_HINTS),
    )


@router.post(
    "/transcriptions",
    response_model=VoiceTranscriptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Transcribe a dictated report for the reporter to check",
)
async def create_transcription(
    user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
    file: Annotated[UploadFile, File()],
    language: Annotated[Literal["en", "ta"] | None, Form()] = None,
) -> VoiceTranscriptRead:
    """Send one recording to the configured speech provider and return what it heard.

    The recording is read in bounded chunks, held in memory for this request only, and
    never stored. The reporter reads the transcript and corrects it before sending it as
    their report.
    """
    if settings.rate_limit_enabled:
        decision = get_rate_limiter().check(
            f"transcribe:{user.id}", settings.rate_limit_transcription_per_minute
        )
        if not decision.allowed:
            raise RateLimitedError(
                "Too many recordings in quick succession. Please type your report — "
                "if this is life-threatening, call your emergency number now.",
                retry_after=decision.retry_after,
            )

    content = bytearray()
    limit = settings.speech_max_bytes
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)
        if len(content) > limit:
            raise MediaTooLargeError(
                f"Recordings must be {limit // (1024 * 1024)} MB or smaller.",
                details={"max_bytes": limit},
            )

    transcript = TranscriptionService(session, settings).transcribe(
        UploadedAudio(content=bytes(content), content_type=file.content_type or ""),
        language_hint=language,
        actor=user,
        context=context,
    )
    return VoiceTranscriptRead.model_validate(transcript)


@router.get(
    "/incidents/{incident_id}/transcripts",
    response_model=list[VoiceTranscriptRead],
    summary="AI transcripts of the dictation behind a report",
)
def list_transcripts(
    incident_id: uuid.UUID, user: IncidentViewer, session: DbSession
) -> list[VoiceTranscriptRead]:
    rows = TranscriptionService(session).list_for_incident(incident_id, actor=user)
    return [VoiceTranscriptRead.model_validate(row) for row in rows]
