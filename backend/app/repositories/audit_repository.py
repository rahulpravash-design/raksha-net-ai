"""Append-only audit log persistence.

There is intentionally no update or delete method on this repository.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import redact
from app.models.enums import UserRole
from app.models.incident import AuditLog


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        action: str,
        actor_id: uuid.UUID | None = None,
        actor_role: UserRole | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            user_agent=user_agent,
            # The same deny-list that protects the logs protects the audit table.
            event_metadata=redact(metadata) if metadata else None,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))
