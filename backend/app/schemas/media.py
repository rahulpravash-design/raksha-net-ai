"""Media response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import MediaType
from app.schemas.common import ORMModel


class MediaRead(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    media_type: MediaType
    content_type: str
    size_bytes: int
    original_filename: str | None
    created_at: datetime
