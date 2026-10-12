"""AI transcripts of voice reports (Phase 9), kept apart from the report itself.

A reporter dictates, reads what the speech model heard, corrects it, and sends it as
their description: the incident holds the reporter's confirmed words. This table holds
what the model heard, labelled AI-derived with its model and confidence
(``CLAUDE.md`` section 2, rules 2 and 3), so an operator can see that a report was
dictated and whether the reporter changed the transcript.

There is no column for the recording, by design: the audio is sent to the provider once
and discarded, and nothing in the schema could store it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VoiceTranscript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_transcripts"

    reporter_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Set when the reporter sends the report the transcript was dictated into. One
    #: transcript per report; NULL while the reporter is still writing it.
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    linked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Whether the description the reporter sent differs from what the model heard.
    #: NULL until the transcript is linked to a report.
    reporter_edited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # -- what the model heard (AI-derived, unverified) -------------------------
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    language_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # -- traceability (CLAUDE.md section 2, rule 3) ------------------------------
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    processing_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # -- what was sent (the recording itself is not kept) -----------------------
    audio_content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    audio_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<VoiceTranscript {self.id} {self.model_name} incident={self.incident_id}>"
        )
