"""Incident business rules: creation, visibility, transitions, priority."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.enums import (
    DISPATCH_ROLES,
    OPERATIONAL_ROLES,
    IncidentCategory,
    IncidentStatus,
    PriorityBand,
    UserRole,
)
from app.models.incident import Incident, IncidentStatusHistory
from app.models.user import User
from app.repositories.incident_repository import IncidentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.incident import (
    IncidentAssign,
    IncidentCreate,
    IncidentPriorityUpdate,
    IncidentStatsSummary,
    IncidentStatusChange,
    IncidentUpdate,
    PriorityAgreementCell,
    PriorityAgreementSummary,
)
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import RequestContext
from app.services.priority import (
    PriorityInput,
    PriorityResult,
    band_for_score,
    calculate_priority,
    load_active_weights,
    resolve_weights,
)
from app.services.status_machine import (
    assert_role_may_transition,
    assert_transition_allowed,
)
from app.utils.codes import generate_reference_code
from app.utils.geo import validate_coordinates
from app.utils.time import utcnow

logger = get_logger(__name__)

#: Retries on the (vanishingly unlikely) collision of a random reference code.
REFERENCE_CODE_ATTEMPTS = 5


class IncidentService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = IncidentRepository(session)
        self.users = UserRepository(session)
        self.audit = AuditService(session)
        #: Resolved once per service instance: which configuration this
        #: deployment currently scores with (Phase 7, docs/ROADMAP.md).
        self.weights = load_active_weights(self.settings)

    # -- creation -----------------------------------------------------------
    def create(
        self,
        payload: IncidentCreate,
        *,
        reporter: User,
        context: RequestContext | None = None,
    ) -> Incident:
        context = context or RequestContext()
        coords = validate_coordinates(payload.latitude, payload.longitude, self.settings)

        incident = Incident(
            reference_code=self._unique_reference_code(),
            reported_by_id=reporter.id,
            category=payload.category,
            description=payload.description,
            location_accuracy_m=payload.location_accuracy_m,
            address_text=payload.address_text,
            landmark=payload.landmark,
            status=IncidentStatus.REPORTED,
            people_affected=payload.people_affected,
            people_trapped=payload.people_trapped,
            medical_required=payload.medical_required,
            immediate_danger=payload.immediate_danger,
            contact_phone=payload.contact_phone or reporter.phone,
        )
        self.repo.set_location(incident, coords)
        self.repo.add(incident)

        self._apply_priority(
            incident,
            calculate_priority(self._priority_input(incident), weights=self.weights),
        )

        self.repo.add_status_history(
            incident_id=incident.id,
            from_status=None,
            to_status=IncidentStatus.REPORTED,
            changed_by_id=reporter.id,
            note="Report submitted by the reporter.",
        )
        self.audit.record(
            AuditAction.INCIDENT_CREATED,
            actor_id=reporter.id,
            actor_role=reporter.role,
            entity_type="incident",
            entity_id=incident.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "category": incident.category.value,
                "priority_band": (
                    incident.priority_band.value if incident.priority_band else None
                ),
            },
        )
        self.session.commit()
        self.session.refresh(incident)

        logger.info(
            "incident_created",
            extra={
                "incident_id": str(incident.id),
                "reference_code": incident.reference_code,
                "category": incident.category.value,
                "priority_band": (
                    incident.priority_band.value if incident.priority_band else None
                ),
            },
        )
        return incident

    # -- reads --------------------------------------------------------------
    def get_for_user(self, incident_id: uuid.UUID, user: User) -> Incident:
        """Fetch an incident the caller is allowed to see.

        A citizen asking for someone else's incident gets ``NotFoundError``, not
        a permission error: the API does not confirm that it exists.
        """
        incident = self.repo.get_detailed(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")
        if not self.can_view(incident, user):
            raise NotFoundError("Incident not found.")
        return incident

    @staticmethod
    def can_view(incident: Incident, user: User) -> bool:
        if user.role in OPERATIONAL_ROLES:
            return True
        return incident.reported_by_id == user.id

    def list_for_user(
        self,
        user: User,
        *,
        offset: int,
        limit: int,
        statuses: Sequence[IncidentStatus] | None = None,
        categories: Sequence[IncidentCategory] | None = None,
        priority_band: PriorityBand | None = None,
        query: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        assigned_to_me: bool = False,
        sort: str = "priority",
        own_only: bool = False,
    ) -> tuple[list[Incident], int]:
        """List incidents, scoped to what the caller may see."""
        restrict_to_reporter: uuid.UUID | None = None
        if own_only or user.role not in OPERATIONAL_ROLES:
            restrict_to_reporter = user.id

        return self.repo.search(
            offset=offset,
            limit=limit,
            reported_by_id=restrict_to_reporter,
            assigned_to_id=user.id if assigned_to_me else None,
            statuses=statuses,
            categories=categories,
            priority_band=priority_band,
            query=query,
            since=since,
            until=until,
            open_only=open_only,
            sort=sort,
        )

    def list_history(
        self, incident_id: uuid.UUID, user: User
    ) -> list[IncidentStatusHistory]:
        self.get_for_user(incident_id, user)  # authorisation
        return self.repo.list_history(incident_id)

    def stats_summary(self) -> IncidentStatsSummary:
        return IncidentStatsSummary(
            total_open=self.repo.count_open(),
            by_band=self.repo.count_by(Incident.priority_band),
            by_status=self.repo.count_by(Incident.status, open_only=False),
            by_category=self.repo.count_by(Incident.category),
            unassigned_open=self.repo.count_unassigned_open(),
        )

    def priority_agreement(self) -> PriorityAgreementSummary:
        """Compare what the engine scored against what dispatchers overrode to.

        The engine's own band is recomputed from the stored score using the
        thresholds of the configuration that produced it, so a deployment that
        has since re-tuned its weights still reads its history correctly.
        """
        total = self.repo.count_all()
        rows = self.repo.overridden_rows()

        tally: dict[tuple[PriorityBand, PriorityBand], int] = {}
        agreement = 0
        for score, override_band, version in rows:
            if score is None or override_band is None:
                continue
            try:
                weights = resolve_weights(version)
            except ValueError:
                # An incident scored under a configuration this deployment no
                # longer carries: count it, but do not guess its bands.
                continue
            engine_band = band_for_score(score, weights=weights)
            if engine_band is override_band:
                agreement += 1
            key = (engine_band, override_band)
            tally[key] = tally.get(key, 0) + 1

        overridden = len(rows)
        return PriorityAgreementSummary(
            total_incidents=total,
            overridden_count=overridden,
            override_rate=round(overridden / total, 4) if total else 0.0,
            agreement_count=agreement,
            disagreement_count=sum(tally.values()) - agreement,
            engine_version=self.weights.version,
            cells=[
                PriorityAgreementCell(
                    engine_band=engine, override_band=override, count=count
                )
                for (engine, override), count in sorted(
                    tally.items(), key=lambda item: -item[1]
                )
            ],
        )

    # -- updates ------------------------------------------------------------
    def update_facts(
        self,
        incident_id: uuid.UUID,
        payload: IncidentUpdate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Incident:
        """Apply an operator's correction of the verified facts.

        Priority is recomputed unless a human has overridden it — an override is
        a decision, and a fact correction must not silently discard it.
        """
        context = context or RequestContext()
        incident = self._get_or_404(incident_id)
        self._assert_dispatch_role(actor)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise ValidationError("No fields were supplied to update.")

        for field, value in changes.items():
            setattr(incident, field, value)

        if not incident.priority_overridden:
            self._apply_priority(
                incident,
                calculate_priority(
                    self._priority_input(incident), now=utcnow(), weights=self.weights
                ),
            )

        self.audit.record(
            AuditAction.INCIDENT_UPDATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident",
            entity_id=incident.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"fields": sorted(changes)},
        )
        self.session.commit()
        self.session.refresh(incident)
        return incident

    def change_status(
        self,
        incident_id: uuid.UUID,
        payload: IncidentStatusChange,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Incident:
        context = context or RequestContext()
        incident = self._get_or_404(incident_id)

        is_owner = incident.reported_by_id == actor.id
        if not is_owner and actor.role not in OPERATIONAL_ROLES:
            raise NotFoundError("Incident not found.")

        previous = incident.status
        assert_transition_allowed(previous, payload.status)
        assert_role_may_transition(
            actor.role, current=previous, target=payload.status, is_owner=is_owner
        )

        if payload.status is IncidentStatus.DUPLICATE:
            self._assert_valid_duplicate_target(incident, payload.duplicate_of_id)
            incident.duplicate_of_id = payload.duplicate_of_id

        incident.status = payload.status
        now = utcnow()
        if payload.status is IncidentStatus.RESOLVED:
            incident.resolved_at = now
        if payload.status is IncidentStatus.CLOSED:
            incident.closed_at = now

        self.repo.add_status_history(
            incident_id=incident.id,
            from_status=previous,
            to_status=payload.status,
            changed_by_id=actor.id,
            note=payload.note,
        )
        self.audit.record(
            AuditAction.INCIDENT_STATUS_CHANGED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident",
            entity_id=incident.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"from": previous.value, "to": payload.status.value},
        )
        self.session.commit()
        self.session.refresh(incident)

        logger.info(
            "incident_status_changed",
            extra={
                "incident_id": str(incident.id),
                "from_status": previous.value,
                "to_status": payload.status.value,
            },
        )
        return incident

    def update_priority(
        self,
        incident_id: uuid.UUID,
        payload: IncidentPriorityUpdate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Incident:
        """Recompute the priority, or record a human override.

        An override keeps the engine's score for comparison but replaces the
        band the control centre queues on, and is always attributable.
        """
        context = context or RequestContext()
        incident = self._get_or_404(incident_id)
        self._assert_dispatch_role(actor)

        result = calculate_priority(
            self._priority_input(incident), now=utcnow(), weights=self.weights
        )

        if payload.override_band is None:
            self._apply_priority(incident, result)
            incident.priority_overridden = False
            incident.priority_override_reason = None
            action = AuditAction.INCIDENT_PRIORITY_RECALCULATED
            metadata = {"score": result.score, "band": result.band.value}
        else:
            self._apply_priority(incident, result)
            incident.priority_band = payload.override_band
            incident.priority_overridden = True
            incident.priority_override_reason = (payload.reason or "").strip()
            action = AuditAction.INCIDENT_PRIORITY_OVERRIDDEN
            metadata = {
                "engine_score": result.score,
                "engine_band": result.band.value,
                "override_band": payload.override_band.value,
                "reason": incident.priority_override_reason,
            }

        self.audit.record(
            action,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident",
            entity_id=incident.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata=metadata,
        )
        self.session.commit()
        self.session.refresh(incident)
        return incident

    def assign(
        self,
        incident_id: uuid.UUID,
        payload: IncidentAssign,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Incident:
        context = context or RequestContext()
        incident = self._get_or_404(incident_id)
        self._assert_dispatch_role(actor)

        if payload.assigned_to_id is not None:
            assignee = self.users.get(payload.assigned_to_id)
            if assignee is None or not assignee.is_active:
                raise ValidationError("The selected user cannot be assigned.")
            if assignee.role not in OPERATIONAL_ROLES:
                raise ValidationError(
                    "Only responders and operators can be assigned to an incident."
                )

        incident.assigned_to_id = payload.assigned_to_id
        self.audit.record(
            AuditAction.INCIDENT_ASSIGNED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident",
            entity_id=incident.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "assigned_to": (
                    str(payload.assigned_to_id) if payload.assigned_to_id else None
                )
            },
        )
        self.session.commit()
        self.session.refresh(incident)
        return incident

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _priority_input(incident: Incident) -> PriorityInput:
        return PriorityInput(
            category=incident.category,
            severity=incident.severity,
            people_affected=incident.people_affected,
            people_trapped=incident.people_trapped,
            medical_required=incident.medical_required,
            immediate_danger=incident.immediate_danger,
            reported_at=incident.created_at,
        )

    @staticmethod
    def _apply_priority(incident: Incident, result: PriorityResult) -> None:
        incident.priority_score = result.score
        incident.priority_band = result.band
        incident.priority_factors = result.factors_as_json()
        incident.priority_engine_version = result.engine_version

    def _get_or_404(self, incident_id: uuid.UUID) -> Incident:
        incident = self.repo.get(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")
        return incident

    @staticmethod
    def _assert_dispatch_role(actor: User) -> None:
        if actor.role not in DISPATCH_ROLES:
            raise ForbiddenError(
                "Only dispatchers and administrators can perform this action."
            )

    def _assert_valid_duplicate_target(
        self, incident: Incident, target_id: uuid.UUID | None
    ) -> None:
        if target_id is None:
            raise ValidationError("duplicate_of_id is required.")
        if target_id == incident.id:
            raise ValidationError("An incident cannot be a duplicate of itself.")
        if self.repo.get(target_id) is None:
            raise ValidationError("The incident it duplicates was not found.")

    def _unique_reference_code(self) -> str:
        for _ in range(REFERENCE_CODE_ATTEMPTS):
            code = generate_reference_code()
            if not self.repo.reference_exists(code):
                return code
        # 28^6 possibilities; five collisions means something is badly wrong.
        raise RuntimeError("Could not allocate a unique incident reference code.")


def role_may_dispatch(role: UserRole) -> bool:
    return role in DISPATCH_ROLES
