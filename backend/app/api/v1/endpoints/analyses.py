"""AI analysis: request a proposal, and record a dispatcher's review of it.

Deliberately not nested under ``incidents.py``: a proposal is not an incident
field, and keeping it in its own module makes that separation obvious rather
than implicit (CLAUDE.md section 2, rule 2).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import Context, DbSession, DispatchUser, OperationalUser
from app.schemas.analysis import AnalysisReview, IncidentAnalysisRead
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/incidents/{incident_id}/analyses", tags=["ai-analysis"])


@router.post(
    "",
    response_model=IncidentAnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request an AI analysis of a report",
)
def run_analysis(
    incident_id: uuid.UUID,
    user: OperationalUser,
    session: DbSession,
    context: Context,
) -> IncidentAnalysisRead:
    """Run the configured analyzer against the citizen's own description.

    This never touches the incident's operational priority: it produces a
    proposal a dispatcher must separately accept, edit or reject.
    """
    analysis = AnalysisService(session).run_analysis(
        incident_id, actor=user, context=context
    )
    return IncidentAnalysisRead.model_validate(analysis)


@router.get(
    "",
    response_model=list[IncidentAnalysisRead],
    summary="List AI analyses for an incident",
)
def list_analyses(
    incident_id: uuid.UUID, user: OperationalUser, session: DbSession
) -> list[IncidentAnalysisRead]:
    rows = AnalysisService(session).list_for_incident(incident_id, actor=user)
    return [IncidentAnalysisRead.model_validate(row) for row in rows]


@router.post(
    "/{analysis_id}/review",
    response_model=IncidentAnalysisRead,
    summary="Accept, edit or reject an AI proposal",
)
def review_analysis(
    incident_id: uuid.UUID,
    analysis_id: uuid.UUID,
    payload: AnalysisReview,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> IncidentAnalysisRead:
    analysis = AnalysisService(session).review(
        incident_id, analysis_id, payload, actor=user, context=context
    )
    return IncidentAnalysisRead.model_validate(analysis)
