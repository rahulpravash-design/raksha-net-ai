"""Incident media upload and retrieval."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile, status

from app.api.deps import AppSettings, Context, CurrentUser, DbSession
from app.core.errors import MediaTooLargeError
from app.schemas.media import MediaRead
from app.services.media_service import MediaService, UploadedFile

router = APIRouter(tags=["media"])


@router.post(
    "/incidents/{incident_id}/media",
    response_model=MediaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a photograph to an incident",
)
async def upload_media(
    incident_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
    file: Annotated[UploadFile, File()],
) -> MediaRead:
    """Upload an image.

    The body is read in bounded chunks so an oversized upload is refused without
    ever being held in full.
    """
    content = bytearray()
    limit = settings.media_max_bytes
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)
        if len(content) > limit:
            raise MediaTooLargeError(
                f"Files must be {limit // (1024 * 1024)} MB or smaller.",
                details={"max_bytes": limit},
            )

    media = MediaService(session, settings).upload(
        incident_id,
        UploadedFile(
            content=bytes(content),
            content_type=file.content_type or "",
            filename=file.filename,
        ),
        actor=user,
        context=context,
    )
    return MediaRead.model_validate(media)


@router.get(
    "/incidents/{incident_id}/media",
    response_model=list[MediaRead],
    summary="List incident media",
)
def list_media(
    incident_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> list[MediaRead]:
    rows = MediaService(session).list_for_incident(incident_id, actor=user)
    return [MediaRead.model_validate(row) for row in rows]


@router.get(
    "/media/{media_id}/content",
    summary="Download media content",
    response_class=Response,
)
def read_media_content(
    media_id: uuid.UUID, user: CurrentUser, session: DbSession, context: Context
) -> Response:
    content, media = MediaService(session).read_content(
        media_id, actor=user, context=context
    )
    return Response(
        content=content,
        media_type=media.content_type,
        headers={
            # Never render an upload inline: an attachment cannot become a
            # stored-XSS vector in the operator's browser.
            "Content-Disposition": f'attachment; filename="{media.id}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )
