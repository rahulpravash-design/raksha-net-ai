"""AI analysis: request a proposal, and apply a human's review of it.

This is the one place the backend calls into ``ai/``. Two rules from
``CLAUDE.md`` section 2 are enforced structurally here, not just by
convention:

* Rule 7 — an unavailable or rejected analysis never blocks or corrupts the
  incident it was requested for; the request simply fails, and the incident is
  triaged from the reporter's own words as it already would be.
* Rule 1 — accepting or editing a proposal does not poke incident fields
  directly. It builds an :class:`~app.schemas.incident.IncidentUpdate` and
  hands it to :meth:`IncidentService.update_facts`, the exact same audited,
  priority-recalculating path a dispatcher's own manual correction takes. AI
  output never has a more direct route to ``incidents`` than a human does.
"""

from __future__ import annotations

import uuid
from typing import Any

from ai.common.interfaces import AnalyzerUnavailable, get_analyzer
from ai.common.schemas import AnalysisRequest, AnalysisResult
from ai.common.validation import AnalysisRejected, validate_analysis
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    AnalysisAlreadyReviewedError,
    AnalysisRejectedError,
    AnalysisUnavailableError,
    ForbiddenError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.models.analysis import IncidentAnalysis
from app.models.enums import (
    DISPATCH_ROLES,
    OPERATIONAL_ROLES,
    AnalysisReviewDecision,
    IncidentCategory,
    SeverityLevel,
)
from app.models.user import User
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.incident_repository import IncidentRepository
from app.schemas.analysis import AnalysisReview
from app.schemas.incident import IncidentUpdate
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import RequestContext
from app.services.incident_service import IncidentService
from app.utils.time import utcnow

logger = get_logger(__name__)


def _safe_category(value: str | None) -> IncidentCategory | None:
    """A model's free-text ``incident_type`` might not name a real category.

    Dropped rather than raised: an analysis that gets everything else right
    should not be discarded over one field that does not parse.
    """
    if value is None:
        return None
    try:
        return IncidentCategory(value)
    except ValueError:
        logger.warning("ai_analysis_unknown_category", extra={"value": value})
        return None


def _safe_severity(value: str | None) -> SeverityLevel | None:
    if value is None:
        return None
    try:
        return SeverityLevel(value)
    except ValueError:
        logger.warning("ai_analysis_unknown_severity", extra={"value": value})
        return None


class AnalysisService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = AnalysisRepository(session)
        self.incidents = IncidentRepository(session)
        self.audit = AuditService(session)

    # -- requesting a proposal ------------------------------------------------
    def run_analysis(
        self,
        incident_id: uuid.UUID,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> IncidentAnalysis:
        context = context or RequestContext()
        if actor.role not in OPERATIONAL_ROLES:
            raise ForbiddenError("Only operational roles may request an AI analysis.")

        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")

        request = AnalysisRequest(
            incident_id=str(incident.id),
            description=incident.description,
            category_hint=incident.category.value,
        )

        try:
            result = get_analyzer(self.settings.ai_enabled).analyze(request)
            result = validate_analysis(result)
        except AnalyzerUnavailable as exc:
            self.audit.record(
                AuditAction.AI_ANALYSIS_UNAVAILABLE,
                actor_id=actor.id,
                actor_role=actor.role,
                entity_type="incident",
                entity_id=incident.id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                metadata={"reason": str(exc)},
            )
            self.session.commit()
            raise AnalysisUnavailableError(str(exc)) from exc
        except AnalysisRejected as exc:
            self.audit.record(
                AuditAction.AI_ANALYSIS_REJECTED,
                actor_id=actor.id,
                actor_role=actor.role,
                entity_type="incident",
                entity_id=incident.id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                metadata={"reasons": exc.reasons},
            )
            self.session.commit()
            raise AnalysisRejectedError(details={"reasons": exc.reasons}) from exc

        analysis = self._persist(incident_id, result)

        self.audit.record(
            AuditAction.AI_ANALYSIS_CREATED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident",
            entity_id=incident.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "analysis_id": str(analysis.id),
                "model_name": result.model_name,
                "model_version": result.model_version,
            },
        )
        self.session.commit()
        self.session.refresh(analysis)

        logger.info(
            "ai_analysis_created",
            extra={
                "incident_id": str(incident.id),
                "analysis_id": str(analysis.id),
                "model_name": result.model_name,
            },
        )
        return analysis

    def _persist(
        self, incident_id: uuid.UUID, result: AnalysisResult
    ) -> IncidentAnalysis:
        analysis = IncidentAnalysis(
            incident_id=incident_id,
            model_name=result.model_name,
            model_version=result.model_version,
            provider=result.provider,
            processing_ms=result.processing_ms,
            proposed_category=_safe_category(result.incident_type),
            type_confidence=result.type_confidence,
            proposed_severity=_safe_severity(result.severity),
            severity_confidence=result.severity_confidence,
            people_affected=result.people_affected,
            people_trapped=result.people_trapped,
            medical_support_required=result.medical_support_required,
            immediate_rescue_required=result.immediate_rescue_required,
            entities=result.entities,
            observations=[obs.model_dump(mode="json") for obs in result.observations],
            reasoning_factors=result.reasoning_factors,
        )
        return self.repo.add(analysis)

    # -- reads ------------------------------------------------------------
    def list_for_incident(
        self, incident_id: uuid.UUID, *, actor: User
    ) -> list[IncidentAnalysis]:
        if actor.role not in OPERATIONAL_ROLES:
            raise ForbiddenError("Only operational roles may view AI analyses.")
        if self.incidents.get(incident_id) is None:
            raise NotFoundError("Incident not found.")
        return self.repo.list_for_incident(incident_id)

    # -- review -----------------------------------------------------------
    def review(
        self,
        incident_id: uuid.UUID,
        analysis_id: uuid.UUID,
        payload: AnalysisReview,
        *,
        actor: User,
        context: RequestContext | None = None,
    ) -> IncidentAnalysis:
        """Apply a dispatcher's decision on one proposal.

        Every field the incident actually receives goes through
        :meth:`IncidentService.update_facts`, so priority is recomputed (unless
        already overridden) and the change is audited exactly as any other
        dispatcher correction would be.
        """
        context = context or RequestContext()
        if actor.role not in DISPATCH_ROLES:
            raise ForbiddenError(
                "Only dispatchers and administrators may review an AI analysis."
            )

        analysis = self.repo.get(analysis_id)
        if analysis is None or analysis.incident_id != incident_id:
            raise NotFoundError("Analysis not found.")
        if analysis.review_decision is not None:
            raise AnalysisAlreadyReviewedError()

        applied_fields: dict[str, Any] = {}
        if payload.decision is AnalysisReviewDecision.ACCEPTED:
            applied_fields = self._proposal_fields(analysis)
        elif payload.decision is AnalysisReviewDecision.EDITED:
            applied_fields = payload.model_dump(
                exclude={"decision", "note"}, exclude_none=True
            )

        if applied_fields:
            IncidentService(self.session, self.settings).update_facts(
                incident_id,
                IncidentUpdate(**applied_fields),
                actor=actor,
                context=context,
            )

        analysis.review_decision = payload.decision
        analysis.reviewed_by_id = actor.id
        analysis.reviewed_at = utcnow()
        analysis.review_note = payload.note
        analysis.applied_fields = (
            {
                key: (value.value if hasattr(value, "value") else value)
                for key, value in applied_fields.items()
            }
            if applied_fields
            else None
        )

        self.audit.record(
            AuditAction.AI_ANALYSIS_REVIEWED,
            actor_id=actor.id,
            actor_role=actor.role,
            entity_type="incident",
            entity_id=incident_id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={
                "analysis_id": str(analysis.id),
                "decision": payload.decision.value,
                "applied_fields": sorted(applied_fields),
            },
        )
        self.session.commit()
        self.session.refresh(analysis)
        return analysis

    @staticmethod
    def _proposal_fields(analysis: IncidentAnalysis) -> dict[str, Any]:
        candidates = {
            "category": analysis.proposed_category,
            "severity": analysis.proposed_severity,
            "people_affected": analysis.people_affected,
            "people_trapped": analysis.people_trapped,
            "medical_required": analysis.medical_support_required,
            "immediate_danger": analysis.immediate_rescue_required,
        }
        return {key: value for key, value in candidates.items() if value is not None}
