"""Dispatch business rules: commit a unit, then follow it to the scene.

Phase 11. The one rule everything here exists to enforce: a dispatch has a
named human approver, always. ``Dispatch.approved_by_id`` is ``NOT NULL`` in
the schema, and this service sets it from the authenticated caller — never
from the request body, so there is no field a client could populate to make a
dispatch look approved when it was not.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.dispatch import Dispatch
from app.models.enums import (
    ALLOWED_DISPATCH_TRANSITIONS,
    CLOSED_DISPATCH_STATUSES,
    DISPATCH_ROLES,
    DISPATCH_TO_RESOURCE_STATUS,
    OPERATIONAL_ROLES,
    TERMINAL_STATUSES,
    DispatchStatus,
    ResourceStatus,
)
from app.models.user import User
from app.repositories.dispatch_repository import DispatchRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.resource_repository import ResourceRepository
from app.schemas.dispatch import DispatchCreate, DispatchStatusChange
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import RequestContext
from app.services.resource_service import estimate_minutes
from app.utils.geo import haversine_km
from app.utils.time import utcnow

logger = get_logger(__name__)

#: Which timestamp each status stamps on arrival.
_STATUS_TIMESTAMPS: dict[DispatchStatus, str] = {
    DispatchStatus.ACKNOWLEDGED: "acknowledged_at",
    DispatchStatus.EN_ROUTE: "en_route_at",
    DispatchStatus.ON_SCENE: "on_scene_at",
}


class DispatchService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = DispatchRepository(session)
        self.incidents = IncidentRepository(session)
        self.resources = ResourceRepository(session)
        self.audit = AuditService(session)

    # -- committing a unit --------------------------------------------------
    def create(
        self,
        incident_id: uuid.UUID,
        payload: DispatchCreate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Dispatch:
        context = context or RequestContext()
        if actor.role not in DISPATCH_ROLES:
            raise ForbiddenError(
                "Only dispatchers and administrators can dispatch a resource."
            )

        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")
        if incident.status in TERMINAL_STATUSES:
            raise ConflictError(
                "That incident is closed; no further resource can be sent.",
                code="INCIDENT_CLOSED",
            )

        resource = self.resources.get(payload.resource_id)
        if resource is None:
            raise NotFoundError("Resource not found.")
        if not resource.is_active:
            raise ValidationError("That resource is not in service.")

        existing = self.repo.active_for_resource(resource.id)
        if existing is not None:
            raise ConflictError(
                f"{resource.call_sign} is already committed to another incident.",
                code="RESOURCE_ALREADY_DISPATCHED",
                details={"dispatch_id": str(existing.id)},
            )

        distance_km = haversine_km(
            float(resource.latitude),
            float(resource.longitude),
            float(incident.latitude),
            float(incident.longitude),
        )
        dispatch = Dispatch(
            incident_id=incident.id,
            resource_id=resource.id,
            # The approver is the authenticated caller, full stop.
            approved_by_id=actor.id,
            status=DispatchStatus.DISPATCHED,
            distance_km=round(distance_km, 3),
            estimated_minutes=estimate_minutes(distance_km),
            note=payload.note,
        )
        self.repo.add(dispatch)

        resource.status = ResourceStatus.DISPATCHED
        resource.status_changed_at = utcnow()

        self.audit.record(
            AuditAction.DISPATCH_CREATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="dispatch",
            entity_id=dispatch.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "incident_id": str(incident.id),
                "resource": resource.call_sign,
                "estimated_minutes": dispatch.estimated_minutes,
            },
        )
        self.session.commit()
        self.session.refresh(dispatch)

        logger.info(
            "dispatch_created",
            extra={
                "dispatch_id": str(dispatch.id),
                "incident_id": str(incident.id),
                "resource": resource.call_sign,
            },
        )
        return dispatch

    # -- following it to the scene -----------------------------------------
    def change_status(
        self,
        dispatch_id: uuid.UUID,
        payload: DispatchStatusChange,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Dispatch:
        """Move a dispatch forward.

        The crew on the unit and the dispatcher who sent them may both do
        this; nobody else can see the dispatch at all.
        """
        context = context or RequestContext()
        dispatch = self._get_visible_or_404(dispatch_id, actor)

        previous = dispatch.status
        allowed = ALLOWED_DISPATCH_TRANSITIONS[previous]
        if payload.status not in allowed:
            raise ConflictError(
                f"A dispatch cannot move from {previous.value} to {payload.status.value}.",
                code="DISPATCH_INVALID_TRANSITION",
                details={"allowed": sorted(item.value for item in allowed)},
            )

        now = utcnow()
        dispatch.status = payload.status
        if payload.note:
            dispatch.note = payload.note
        if payload.status is DispatchStatus.CANCELLED:
            dispatch.cancel_reason = (payload.reason or "").strip()

        stamp = _STATUS_TIMESTAMPS.get(payload.status)
        if stamp is not None:
            setattr(dispatch, stamp, now)
        if payload.status in CLOSED_DISPATCH_STATUSES:
            dispatch.closed_at = now

        # The unit's own availability follows what its crew reports.
        resource = self.resources.get(dispatch.resource_id)
        if resource is not None:
            resource.status = DISPATCH_TO_RESOURCE_STATUS[payload.status]
            resource.status_changed_at = now

        self.audit.record(
            AuditAction.DISPATCH_STATUS_CHANGED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="dispatch",
            entity_id=dispatch.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"from": previous.value, "to": payload.status.value},
        )
        self.session.commit()
        self.session.refresh(dispatch)
        return dispatch

    # -- reads --------------------------------------------------------------
    def get_for_user(self, dispatch_id: uuid.UUID, actor: User) -> Dispatch:
        return self._get_visible_or_404(dispatch_id, actor)

    def list_for_incident(self, incident_id: uuid.UUID, *, actor: User) -> list[Dispatch]:
        if actor.role not in OPERATIONAL_ROLES:
            raise ForbiddenError("Only operational roles can view dispatches.")
        if self.incidents.get(incident_id) is None:
            raise NotFoundError("Incident not found.")
        return self.repo.list_for_incident(incident_id)

    def list_my_assignments(
        self, actor: User, *, open_only: bool = True
    ) -> list[Dispatch]:
        """What the responder application shows its user.

        Scoped by the units the caller operates, so a responder sees their own
        assignments and nobody else's.
        """
        if actor.role not in OPERATIONAL_ROLES:
            raise ForbiddenError("Only operational roles have assignments.")
        return self.repo.list_for_operator(actor.id, open_only=open_only)

    # -- internals ----------------------------------------------------------
    def _get_visible_or_404(self, dispatch_id: uuid.UUID, actor: User) -> Dispatch:
        dispatch = self.repo.get(dispatch_id)
        if dispatch is None:
            raise NotFoundError("Dispatch not found.")

        if actor.role in DISPATCH_ROLES:
            return dispatch

        resource = self.resources.get(dispatch.resource_id)
        if resource is not None and resource.operator_id == actor.id:
            return dispatch

        # Someone else's assignment reads as absent, not as forbidden.
        raise NotFoundError("Dispatch not found.")
