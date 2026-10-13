"""Voice reports: transcribe a reporter's dictation, and attach it to their report.

Three rules from ``CLAUDE.md`` section 2 shape this module:

* Rule 7: dictation sits in front of the report form, never in its way. With no provider
  configured, or a provider that fails, the reporter is told to type; and filing a report
  never depends on its transcript (one that cannot be attached is logged, not fatal).
* Rules 2 and 3: what the model heard is stored in ``voice_transcripts`` with its model
  and confidence, never in ``incidents``. The incident's description is what the reporter
  sent after reading the transcript and correcting it.
* Rule 4, in spirit: an operator can see that a report was dictated and whether the
  reporter changed the model's words, rather than taking either on trust.

The recording is held in memory for one request and sent to the provider once. It is
never written to disk or to the database (``docs/AI_ARCHITECTURE.md`` section 11).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from ai.common.interfaces import (
    NoSpeechRecognised,
    SpeechConfig,
    TranscriptionUnavailable,
    get_transcriber,
)
from ai.common.schemas import SPEECH_LANGUAGE_HINTS
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    ForbiddenError,
    MediaTooLargeError,
    NoSpeechRecognisedError,
    NotFoundError,
    TranscriptionUnavailableError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.enums import INCIDENT_VIEW_ROLES
from app.models.incident import Incident
from app.models.transcript import VoiceTranscript
from app.models.user import User
from app.repositories.incident_repository import IncidentRepository
from app.repositories.transcript_repository import TranscriptRepository
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import RequestContext
from app.utils.audio import ACCEPTED_AUDIO_TYPES, sniff_audio_type
from app.utils.time import utcnow

logger = get_logger(__name__)

#: A transcript that never became part of a report is a person's words with no report
#: attached. It is removed once it is this old, but only opportunistically: whenever anyone
#: next dictates. There is no scheduler yet (docs/DATABASE.md section 6), so a transcript
#: can outlive this if nobody dictates afterwards.
UNLINKED_RETENTION = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class UploadedAudio:
    """A recording already read into memory and bounded by the size cap."""

    content: bytes
    content_type: str


def _same_words(a: str, b: str) -> bool:
    return " ".join(a.split()) == " ".join(b.split())


class TranscriptionService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = TranscriptRepository(session)
        self.incidents = IncidentRepository(session)
        self.audit = AuditService(session)

    # -- availability -------------------------------------------------------------
    def is_available(self) -> bool:
        return self._speech_config() is not None

    def _speech_config(self) -> SpeechConfig | None:
        """A speech provider, when this deployment has configured one and AI is on."""
        settings = self.settings
        if not (
            settings.ai_enabled and settings.speech_provider and settings.speech_api_key
        ):
            return None
        return SpeechConfig(
            provider=settings.speech_provider,
            api_key=settings.speech_api_key.get_secret_value(),
            model=settings.speech_model,
            base_url=settings.speech_base_url,
            timeout_seconds=float(settings.speech_timeout_seconds),
        )

    # -- transcription ------------------------------------------------------------
    def transcribe(
        self,
        audio: UploadedAudio,
        *,
        language_hint: str | None,
        actor: User,
        context: RequestContext | None = None,
    ) -> VoiceTranscript:
        context = context or RequestContext()
        config = self._speech_config()
        if config is None:
            # Nothing is read or sent: the deployment offers typing only.
            raise TranscriptionUnavailableError()
        if language_hint is not None and language_hint not in SPEECH_LANGUAGE_HINTS:
            raise ValidationError(
                "Unknown language.", details={"allowed": sorted(SPEECH_LANGUAGE_HINTS)}
            )
        content_type = self._validate(audio)

        transcriber = get_transcriber(self.settings.ai_enabled, config)
        try:
            result = transcriber.transcribe(
                audio.content, media_type=content_type, language=language_hint
            )
        except TranscriptionUnavailable as exc:
            # The recording did reach the provider (or was attempted): that is a
            # transfer of the reporter's voice, and is recorded as one.
            self._record_failure(actor, context, audio, content_type, reason=str(exc))
            if isinstance(exc, NoSpeechRecognised):
                raise NoSpeechRecognisedError() from exc
            # The reporter is told to type; the provider's reason is for operators.
            logger.warning("voice_transcription_unavailable", extra={"reason": str(exc)})
            raise TranscriptionUnavailableError() from exc

        self.repo.delete_unlinked_before(utcnow() - UNLINKED_RETENTION)
        transcript = self.repo.add(
            VoiceTranscript(
                reporter_id=actor.id,
                text=result.text,
                confidence=result.confidence,
                language=result.language,
                language_hint=language_hint,
                duration_seconds=result.duration_seconds,
                model_name=result.model_name,
                model_version=result.model_version,
                provider=result.provider,
                processing_ms=result.processing_ms,
                audio_content_type=content_type,
                audio_size_bytes=len(audio.content),
            )
        )
        self.audit.record(
            AuditAction.AI_TRANSCRIPTION_CREATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="voice_transcript",
            entity_id=transcript.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                # What left the platform, and to whom. Never the words themselves.
                "provider": result.provider,
                "model_name": result.model_name,
                "model_version": result.model_version,
                "audio_content_type": content_type,
                "audio_size_bytes": len(audio.content),
                "language_hint": language_hint,
                "confidence": result.confidence,
            },
        )
        self.session.commit()
        self.session.refresh(transcript)
        logger.info(
            "voice_transcript_created",
            extra={"transcript_id": str(transcript.id), "model_name": result.model_name},
        )
        return transcript

    def _record_failure(
        self,
        actor: User,
        context: RequestContext,
        audio: UploadedAudio,
        content_type: str,
        *,
        reason: str,
    ) -> None:
        self.audit.record(
            AuditAction.AI_TRANSCRIPTION_UNAVAILABLE,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="user",
            entity_id=actor.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "reason": reason,
                "provider": self.settings.speech_provider,
                "audio_content_type": content_type,
                "audio_size_bytes": len(audio.content),
            },
        )
        self.session.commit()

    def _validate(self, audio: UploadedAudio) -> str:
        if not audio.content:
            raise ValidationError("The recording is empty.")
        limit = self.settings.speech_max_bytes
        if len(audio.content) > limit:
            raise MediaTooLargeError(
                f"Recordings must be {limit // (1024 * 1024)} MB or smaller.",
                details={"max_bytes": limit},
            )
        declared = (audio.content_type or "").split(";")[0].strip().lower()
        if declared not in ACCEPTED_AUDIO_TYPES:
            raise UnsupportedMediaTypeError(
                "Only WebM, Ogg and MP4 audio recordings are accepted.",
                details={"allowed": list(ACCEPTED_AUDIO_TYPES)},
            )
        if sniff_audio_type(audio.content) != declared:
            raise UnsupportedMediaTypeError(
                "The file contents do not match the declared file type."
            )
        return declared

    # -- the report it was dictated into --------------------------------------------
    def attach_to_incident(
        self, transcript_id: uuid.UUID, incident: Incident, *, reporter: User
    ) -> bool:
        """Link the reporter's own unlinked transcript to their new report.

        Never raises for a transcript that is missing, someone else's, or already used:
        the report is what matters, and it is filed either way. The caller commits.
        """
        transcript = self.repo.get(transcript_id)
        linked = transcript is not None and self.repo.link(
            transcript_id,
            reporter_id=reporter.id,
            incident_id=incident.id,
            reporter_edited=not _same_words(transcript.text, incident.description),
            at=utcnow(),
        )
        if not linked:
            logger.warning(
                "voice_transcript_not_linked",
                extra={
                    "transcript_id": str(transcript_id),
                    "incident_id": str(incident.id),
                },
            )
        return linked

    # -- reading --------------------------------------------------------------------
    def list_for_incident(
        self, incident_id: uuid.UUID, *, actor: User
    ) -> list[VoiceTranscript]:
        if actor.role not in INCIDENT_VIEW_ROLES:
            raise ForbiddenError("Only operational roles may view voice transcripts.")
        if self.incidents.get(incident_id) is None:
            raise NotFoundError("Incident not found.")
        return self.repo.list_for_incident(incident_id)
