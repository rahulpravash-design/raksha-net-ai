"""Media upload, validation and retrieval.

Upload handling is the highest-risk input path in the platform, so the checks
here are deliberately layered: size, declared type, sniffed type, and a
generated storage key that never derives from client input
(``docs/SECURITY.md`` section 5).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    ForbiddenError,
    MediaTooLargeError,
    NotFoundError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.enums import OPERATIONAL_ROLES, MediaType
from app.models.incident import Incident, IncidentMedia
from app.models.user import User
from app.repositories.incident_repository import IncidentRepository
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import RequestContext

logger = get_logger(__name__)

#: Magic-byte signatures for the formats we accept. The declared content type
#: must agree with what the bytes actually are.
MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),  # plus a "WEBP" marker at offset 8, checked below
}

EXTENSION_FOR_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

SNIFF_BYTES = 16


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """A file already read into memory and bounded by the size cap."""

    content: bytes
    content_type: str
    filename: str | None


class MediaService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = IncidentRepository(session)
        self.audit = AuditService(session)

    # -- upload -------------------------------------------------------------
    def upload(
        self,
        incident_id: uuid.UUID,
        file: UploadedFile,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> IncidentMedia:
        context = context or RequestContext()
        incident = self._get_incident_for(actor, incident_id)

        content_type = self._validate(file)
        checksum = hashlib.sha256(file.content).hexdigest()
        storage_key = self._storage_key(incident.id, content_type)

        destination = self._absolute_path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(file.content)

        media = IncidentMedia(
            incident_id=incident.id,
            uploaded_by_id=actor.id,
            media_type=MediaType.IMAGE,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(file.content),
            checksum_sha256=checksum,
            original_filename=self._safe_display_name(file.filename),
        )
        self.repo.add_media(media)
        self.audit.record(
            AuditAction.MEDIA_UPLOADED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident_media",
            entity_id=media.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "incident_id": str(incident.id),
                "content_type": content_type,
                "size_bytes": media.size_bytes,
            },
        )
        self.session.commit()
        self.session.refresh(media)
        return media

    # -- read ---------------------------------------------------------------
    def list_for_incident(
        self, incident_id: uuid.UUID, *, actor: User
    ) -> list[IncidentMedia]:
        self._get_incident_for(actor, incident_id, require_write=False)
        return self.repo.list_media(incident_id)

    def read_content(
        self,
        media_id: uuid.UUID,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> tuple[bytes, IncidentMedia]:
        context = context or RequestContext()
        media = self.repo.get_media(media_id)
        if media is None:
            raise NotFoundError("Media not found.")

        self._get_incident_for(actor, media.incident_id, require_write=False)

        path = self._absolute_path(media.storage_key)
        if not path.is_file():
            # The row exists but the object does not — a storage fault, not a
            # client error. Surface it rather than returning empty bytes.
            logger.error(
                "media_object_missing",
                extra={"media_id": str(media.id), "storage_key": media.storage_key},
            )
            raise NotFoundError("The stored file is no longer available.")

        self.audit.record(
            AuditAction.MEDIA_ACCESSED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident_media",
            entity_id=media.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
        self.session.commit()
        return path.read_bytes(), media

    # -- validation ---------------------------------------------------------
    def _validate(self, file: UploadedFile) -> str:
        if not file.content:
            raise ValidationError("The uploaded file is empty.")

        if len(file.content) > self.settings.media_max_bytes:
            raise MediaTooLargeError(
                f"Files must be {self.settings.media_max_bytes // (1024 * 1024)} MB or smaller.",
                details={"max_bytes": self.settings.media_max_bytes},
            )

        declared = (file.content_type or "").split(";")[0].strip().lower()
        if declared not in self.settings.media_allowed_mime:
            raise UnsupportedMediaTypeError(
                "Only JPEG, PNG and WebP images are accepted.",
                details={"allowed": self.settings.media_allowed_mime},
            )

        if not self._matches_magic(file.content, declared):
            # A mismatch means the file is not what it claims to be. That is the
            # classic disguised-payload upload, so it is refused outright.
            raise UnsupportedMediaTypeError(
                "The file contents do not match the declared file type."
            )

        return declared

    @staticmethod
    def _matches_magic(content: bytes, content_type: str) -> bool:
        signatures = MAGIC_SIGNATURES.get(content_type)
        if not signatures:
            return False
        header = content[:SNIFF_BYTES]
        if not any(header.startswith(signature) for signature in signatures):
            return False
        if content_type == "image/webp":
            return len(content) >= 12 and content[8:12] == b"WEBP"
        return True

    @staticmethod
    def _safe_display_name(filename: str | None) -> str | None:
        """Keep the client filename for display only, stripped of any path.

        It is never used to build a storage path, but a traversal-looking name
        should not be echoed back into a UI either.
        """
        if not filename:
            return None
        return Path(filename).name[:255] or None

    @staticmethod
    def _storage_key(incident_id: uuid.UUID, content_type: str) -> str:
        extension = EXTENSION_FOR_MIME.get(content_type, ".bin")
        return f"{incident_id}/{uuid.uuid4().hex}{extension}"

    def _absolute_path(self, storage_key: str) -> Path:
        root = Path(self.settings.media_storage_path).resolve()
        candidate = (root / storage_key).resolve()
        # Defence in depth: keys are generated, but a path that escapes the
        # storage root must never be opened.
        if not candidate.is_relative_to(root):
            raise ValidationError("Invalid storage key.")
        return candidate

    def _get_incident_for(
        self, actor: User, incident_id: uuid.UUID, *, require_write: bool = True
    ) -> Incident:
        incident = self.repo.get(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")

        is_owner = incident.reported_by_id == actor.id
        if actor.role in OPERATIONAL_ROLES or is_owner:
            if require_write and not (is_owner or actor.role in OPERATIONAL_ROLES):
                raise ForbiddenError("You cannot add media to this incident.")
            return incident

        raise NotFoundError("Incident not found.")
