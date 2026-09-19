"""Thin helper around the audit repository.

Centralising the action vocabulary keeps audit entries greppable and stops the
same event being recorded under three different names.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.repositories.audit_repository import AuditRepository


class AuditAction:
    LOGIN_SUCCESS = "auth.login_success"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    TOKEN_REFRESHED = "auth.token_refreshed"  # noqa: S105 - an action name
    TOKEN_REUSE_DETECTED = "auth.token_reuse_detected"  # noqa: S105 - an action name
    USER_REGISTERED = "user.registered"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_DEACTIVATED = "user.deactivated"
    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_STATUS_CHANGED = "incident.status_changed"
    INCIDENT_PRIORITY_RECALCULATED = "incident.priority_recalculated"
    INCIDENT_PRIORITY_OVERRIDDEN = "incident.priority_overridden"
    INCIDENT_ASSIGNED = "incident.assigned"
    MEDIA_UPLOADED = "media.uploaded"
    MEDIA_ACCESSED = "media.accessed"
    RESOURCE_CREATED = "resource.created"
    RESOURCE_UPDATED = "resource.updated"
    RESOURCE_STATUS_CHANGED = "resource.status_changed"
    AI_ANALYSIS_CREATED = "ai.analysis_created"
    AI_ANALYSIS_UNAVAILABLE = "ai.analysis_unavailable"
    AI_ANALYSIS_REJECTED = "ai.analysis_rejected"
    AI_ANALYSIS_REVIEWED = "ai.analysis_reviewed"


class AuditService:
    def __init__(self, session: Session) -> None:
        self.repo = AuditRepository(session)

    def record(
        self,
        action: str,
        *,
        actor_id: uuid.UUID | None = None,
        actor_role: UserRole | None = None,
        entity_type: str | None = None,
        entity_id: str | uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.repo.record(
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata,
        )
