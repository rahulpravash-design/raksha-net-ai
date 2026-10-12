"""Persistence for AI transcripts of voice reports."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.transcript import VoiceTranscript


class TranscriptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, transcript: VoiceTranscript) -> VoiceTranscript:
        self.session.add(transcript)
        self.session.flush()
        return transcript

    def get(self, transcript_id: uuid.UUID) -> VoiceTranscript | None:
        return self.session.get(VoiceTranscript, transcript_id)

    def list_for_incident(self, incident_id: uuid.UUID) -> list[VoiceTranscript]:
        stmt = (
            select(VoiceTranscript)
            .where(VoiceTranscript.incident_id == incident_id)
            .order_by(VoiceTranscript.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def link(
        self,
        transcript_id: uuid.UUID,
        *,
        reporter_id: uuid.UUID,
        incident_id: uuid.UUID,
        reporter_edited: bool,
        at: datetime,
    ) -> bool:
        """Attach a reporter's unlinked transcript to a report, atomically.

        One conditional UPDATE, so two reports sent at once with the same transcript
        cannot both claim it. False when nothing matched.
        """
        result = self.session.execute(
            update(VoiceTranscript)
            .where(VoiceTranscript.id == transcript_id)
            .where(VoiceTranscript.reporter_id == reporter_id)
            .where(VoiceTranscript.incident_id.is_(None))
            .values(
                incident_id=incident_id, reporter_edited=reporter_edited, linked_at=at
            )
            .execution_options(synchronize_session="fetch")
        )
        return bool(getattr(result, "rowcount", 0))

    def delete_unlinked_before(self, before: datetime) -> int:
        """Remove transcripts older than ``before`` that never became part of a report."""
        result = self.session.execute(
            delete(VoiceTranscript)
            .where(VoiceTranscript.incident_id.is_(None))
            .where(VoiceTranscript.created_at < before)
        )
        return int(getattr(result, "rowcount", 0) or 0)
