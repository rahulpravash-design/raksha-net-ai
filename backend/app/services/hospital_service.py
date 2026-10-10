"""Hospital coordination: capacity, and telling a hospital what is coming.

Phase 12's constraint is what the hospital is *not* told. The notice is built
here, from the incident's category and severity plus what the dispatcher
deliberately writes — never from the reporter's record. The schema has no
column for the reporter, so there is no path by which their identity could
reach a receiving facility.
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
from app.models.enums import (
    ADMIN_ROLES,
    ALLOWED_NOTICE_TRANSITIONS,
    DISPATCH_ROLES,
    INCIDENT_VIEW_ROLES,
    OPERATIONAL_ROLES,
    HospitalNoticeStatus,
    UserRole,
)
from app.models.hospital import Hospital, InboundPatientNotice
from app.models.user import User
from app.repositories.dispatch_repository import DispatchRepository
from app.repositories.hospital_repository import HospitalRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.hospital import (
    HospitalCapacityUpdate,
    HospitalCreate,
    InboundNoticeCreate,
    InboundNoticeStatusChange,
    NearbyHospital,
)
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import RequestContext
from app.utils.geo import validate_coordinates
from app.utils.time import utcnow

logger = get_logger(__name__)


class HospitalService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = HospitalRepository(session)
        self.incidents = IncidentRepository(session)
        self.dispatches = DispatchRepository(session)
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    # -- hospitals ----------------------------------------------------------
    def create(
        self,
        payload: HospitalCreate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Hospital:
        context = context or RequestContext()
        if actor.role not in ADMIN_ROLES:
            raise ForbiddenError("Only administrators can register a hospital.")

        if self.repo.get_by_code(payload.code) is not None:
            raise ConflictError(
                "A hospital with that code already exists.",
                code="HOSPITAL_CODE_TAKEN",
            )

        coords = validate_coordinates(payload.latitude, payload.longitude, self.settings)
        hospital = Hospital(
            code=payload.code,
            name=payload.name,
            address=payload.address,
            contact_phone=payload.contact_phone,
            total_beds=payload.total_beds,
            available_beds=payload.available_beds,
            icu_total=payload.icu_total,
            icu_available=payload.icu_available,
            specialties=[item.strip().lower() for item in payload.specialties],
            managed_by_id=self._validated_manager(payload.managed_by_id),
            capacity_updated_at=utcnow(),
        )
        self.repo.set_location(hospital, coords)
        self.repo.add(hospital)

        self.audit.record(
            AuditAction.HOSPITAL_CREATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="hospital",
            entity_id=hospital.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"code": hospital.code},
        )
        self.session.commit()
        self.session.refresh(hospital)
        return hospital

    def update_capacity(
        self,
        hospital_id: uuid.UUID,
        payload: HospitalCapacityUpdate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> Hospital:
        """Report current capacity.

        The hospital's own operator maintains this, because they are the only
        party who knows it. A dispatcher may also correct it, which is audited
        the same way.
        """
        context = context or RequestContext()
        hospital = self._get_or_404(hospital_id)

        manages_this = hospital.managed_by_id == actor.id
        if actor.role not in DISPATCH_ROLES and not manages_this:
            raise ForbiddenError("You do not maintain this hospital's capacity.")

        changes = payload.model_dump(exclude_unset=True, exclude={"note"})
        if not changes:
            raise ValidationError("No capacity fields were supplied.")

        if "specialties" in changes and changes["specialties"] is not None:
            changes["specialties"] = [
                item.strip().lower() for item in changes["specialties"]
            ]

        for field, value in changes.items():
            if value is not None:
                setattr(hospital, field, value)

        if hospital.available_beds > hospital.total_beds:
            raise ValidationError("available_beds cannot exceed total_beds.")
        if hospital.icu_available > hospital.icu_total:
            raise ValidationError("icu_available cannot exceed icu_total.")

        hospital.capacity_updated_at = utcnow()

        self.audit.record(
            AuditAction.HOSPITAL_CAPACITY_UPDATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="hospital",
            entity_id=hospital.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"fields": sorted(changes), "note": payload.note},
        )
        self.session.commit()
        self.session.refresh(hospital)
        return hospital

    def get_for_user(self, hospital_id: uuid.UUID, actor: User) -> Hospital:
        self._assert_operational(actor)
        return self._get_or_404(hospital_id)

    def list_for_user(
        self, actor: User, *, offset: int, limit: int, active_only: bool = True
    ) -> tuple[list[Hospital], int]:
        self._assert_operational(actor)
        return self.repo.list_all(offset=offset, limit=limit, active_only=active_only)

    def find_nearby(
        self,
        actor: User,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        accepting_only: bool = True,
        needs_icu: bool = False,
        limit: int = 20,
    ) -> list[NearbyHospital]:
        self._assert_operational(actor)
        coords = validate_coordinates(latitude, longitude, self.settings)
        capped = min(radius_km, self.settings.geo_max_search_radius_km)
        lat, lon = coords.as_floats
        rows = self.repo.find_nearby(
            latitude=lat,
            longitude=lon,
            radius_km=capped,
            accepting_only=accepting_only,
            needs_icu=needs_icu,
            limit=limit,
        )
        return [NearbyHospital(**row) for row in rows]

    # -- inbound notices ----------------------------------------------------
    def create_notice(
        self,
        incident_id: uuid.UUID,
        payload: InboundNoticeCreate,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> InboundPatientNotice:
        context = context or RequestContext()
        if actor.role not in DISPATCH_ROLES:
            raise ForbiddenError(
                "Only dispatchers and administrators can notify a hospital."
            )

        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")

        hospital = self.repo.get(payload.hospital_id)
        if hospital is None or not hospital.is_active:
            raise NotFoundError("Hospital not found.")

        if payload.dispatch_id is not None:
            dispatch = self.dispatches.get(payload.dispatch_id)
            if dispatch is None or dispatch.incident_id != incident.id:
                raise ValidationError("That dispatch does not belong to this incident.")

        notice = InboundPatientNotice(
            hospital_id=hospital.id,
            incident_id=incident.id,
            dispatch_id=payload.dispatch_id,
            created_by_id=actor.id,
            status=HospitalNoticeStatus.NOTIFIED,
            patient_count=payload.patient_count,
            # Category and severity travel; the report text does not.
            category=incident.category,
            severity=payload.severity or incident.severity,
            eta_minutes=payload.eta_minutes,
            clinical_notes=payload.clinical_notes,
        )
        self.repo.add_notice(notice)

        self.audit.record(
            AuditAction.HOSPITAL_NOTICE_SENT,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="hospital_notice",
            entity_id=notice.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "hospital": hospital.code,
                "incident_id": str(incident.id),
                "patient_count": notice.patient_count,
            },
        )
        self.session.commit()
        self.session.refresh(notice)

        logger.info(
            "hospital_notice_sent",
            extra={"notice_id": str(notice.id), "hospital": hospital.code},
        )
        return notice

    def respond_to_notice(
        self,
        notice_id: uuid.UUID,
        payload: InboundNoticeStatusChange,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> InboundPatientNotice:
        """The receiving hospital acknowledges, diverts, or confirms arrival."""
        context = context or RequestContext()
        notice = self._get_visible_notice_or_404(notice_id, actor)

        previous = notice.status
        allowed = ALLOWED_NOTICE_TRANSITIONS[previous]
        if payload.status not in allowed:
            raise ConflictError(
                f"A notice cannot move from {previous.value} to {payload.status.value}.",
                code="NOTICE_INVALID_TRANSITION",
                details={"allowed": sorted(item.value for item in allowed)},
            )

        now = utcnow()
        notice.status = payload.status
        if payload.response_note:
            notice.response_note = payload.response_note
        if payload.status is HospitalNoticeStatus.ACKNOWLEDGED:
            notice.acknowledged_at = now
        if payload.status in (
            HospitalNoticeStatus.ARRIVED,
            HospitalNoticeStatus.DIVERTED,
            HospitalNoticeStatus.CANCELLED,
        ):
            notice.closed_at = now

        self.audit.record(
            AuditAction.HOSPITAL_NOTICE_UPDATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="hospital_notice",
            entity_id=notice.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"from": previous.value, "to": payload.status.value},
        )
        self.session.commit()
        self.session.refresh(notice)
        return notice

    def list_notices_for_hospital(
        self, hospital_id: uuid.UUID, *, actor: User, open_only: bool = True
    ) -> list[InboundPatientNotice]:
        hospital = self._get_or_404(hospital_id)
        manages_this = hospital.managed_by_id == actor.id
        if actor.role not in DISPATCH_ROLES and not manages_this:
            raise NotFoundError("Hospital not found.")
        return self.repo.list_notices_for_hospital(hospital_id, open_only=open_only)

    def list_notices_for_incident(
        self, incident_id: uuid.UUID, *, actor: User
    ) -> list[InboundPatientNotice]:
        # Notices across every hospital for an incident are a dispatcher's view;
        # a hospital sees only its own (list_notices_for_hospital).
        if actor.role not in INCIDENT_VIEW_ROLES:
            raise ForbiddenError(
                "Only dispatch-side roles can view an incident's notices."
            )
        if self.incidents.get(incident_id) is None:
            raise NotFoundError("Incident not found.")
        return self.repo.list_notices_for_incident(incident_id)

    # -- internals ----------------------------------------------------------
    def _get_or_404(self, hospital_id: uuid.UUID) -> Hospital:
        hospital = self.repo.get(hospital_id)
        if hospital is None:
            raise NotFoundError("Hospital not found.")
        return hospital

    def _get_visible_notice_or_404(
        self, notice_id: uuid.UUID, actor: User
    ) -> InboundPatientNotice:
        notice = self.repo.get_notice(notice_id)
        if notice is None:
            raise NotFoundError("Notice not found.")
        if actor.role in DISPATCH_ROLES:
            return notice
        hospital = self.repo.get(notice.hospital_id)
        if hospital is not None and hospital.managed_by_id == actor.id:
            return notice
        raise NotFoundError("Notice not found.")

    def _validated_manager(self, manager_id: uuid.UUID | None) -> uuid.UUID | None:
        if manager_id is None:
            return None
        manager = self.users.get(manager_id)
        if manager is None or not manager.is_active:
            raise ValidationError("The selected manager cannot be assigned.")
        if manager.role not in (UserRole.HOSPITAL_OPERATOR, *ADMIN_ROLES):
            raise ValidationError(
                "Only a hospital operator or administrator can manage a hospital."
            )
        return manager_id

    @staticmethod
    def _assert_operational(actor: User) -> None:
        if actor.role not in OPERATIONAL_ROLES:
            raise ForbiddenError("Only operational roles can view hospitals.")
