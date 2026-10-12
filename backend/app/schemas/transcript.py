"""Voice-report transcription schemas (Phase 9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import ORMModel


class TranscriptionAvailability(BaseModel):
    """Whether the report form should offer dictation, and within what limits."""

    available: bool
    max_bytes: int
    accepted_types: list[str]
    languages: list[str]


class VoiceTranscriptRead(ORMModel):
    """What a speech model heard. AI-derived and unverified; never the report itself."""

    id: uuid.UUID
    incident_id: uuid.UUID | None
    #: Always "AI_TRANSCRIPT": a client cannot mistake this for the reporter's words.
    source: Literal["AI_TRANSCRIPT"] = "AI_TRANSCRIPT"
    text: str
    confidence: float
    language: str | None
    language_hint: str | None
    duration_seconds: float | None
    model_name: str
    model_version: str
    provider: str
    reporter_edited: bool | None
    created_at: datetime
