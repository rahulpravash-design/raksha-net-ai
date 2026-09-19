"""Incident reporting and management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    AppSettings,
    Context,
    CurrentUser,
    DbSession,
    DispatchUser,
    OperationalUser,
)
from app.core.errors import RateLimitedError
from app.core.rate_limit import get_rate_limiter
from app.models.enums import IncidentCategory, IncidentStatus, PriorityBand
from app.schemas.common import Page
from app.schemas.incident import (
    IncidentAssign,
    IncidentCreate,
    IncidentPriorityUpdate,
    IncidentRead,
    IncidentStatsSummary,
    IncidentStatusChange,
    IncidentStatusHistoryRead,
    IncidentSummary,
    IncidentUpdate,
    PriorityAgreementSummary,
)
from app.services.incident_service import IncidentService

router = APIRouter(prefix="/incidents", tags=["incidents"])

SortOption = Annotated[str, Query(pattern="^(priority|created_at|-created_at)$")]


@router.post(
    "",
    response_model=IncidentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Report an emergency",
)
def create_incident(
    payload: IncidentCreate,
    user: CurrentUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> IncidentRead:
    """Submit an emergency report.

    The rate limit here is deliberately generous: throttling must never become a
    denial of service against a genuine emergency.
    """
    if settings.rate_limit_enabled:
        decision = get_rate_limiter().check(
            f"report:{user.id}", settings.rate_limit_report_per_minute
        )
        if not decision.allowed:
            raise RateLimitedError(
                "You have submitted several reports in quick succession. "
                "If this is a new emergency, please call the emergency number.",
                retry_after=decision.retry_after,
            )

    incident = IncidentService(session, settings).create(
        payload, reporter=user, context=context
    )
    return IncidentRead.model_validate(incident)


@router.get("/mine", response_model=Page[IncidentSummary], summary="Own reports")
def list_my_incidents(
    user: CurrentUser,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    sort: SortOption = "-created_at",
) -> Page[IncidentSummary]:
    rows, total = IncidentService(session).list_for_user(
        user,
        offset=(page - 1) * page_size,
        limit=page_size,
        sort=sort,
        own_only=True,
    )
    return Page.build(
        [IncidentSummary.model_validate(row) for row in rows], total, page, page_size
    )


@router.get("", response_model=Page[IncidentSummary], summary="Incident queue")
def list_incidents(
    user: OperationalUser,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    status_filter: Annotated[list[IncidentStatus] | None, Query(alias="status")] = None,
    category: Annotated[list[IncidentCategory] | None, Query()] = None,
    priority_band: PriorityBand | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    open_only: bool = False,
    assigned_to_me: bool = False,
    sort: SortOption = "priority",
) -> Page[IncidentSummary]:
    """The control-centre queue: most urgent first, oldest first within a band."""
    rows, total = IncidentService(session).list_for_user(
        user,
        offset=(page - 1) * page_size,
        limit=page_size,
        statuses=status_filter,
        categories=category,
        priority_band=priority_band,
        query=q,
        since=since,
        until=until,
        open_only=open_only,
        assigned_to_me=assigned_to_me,
        sort=sort,
    )
    return Page.build(
        [IncidentSummary.model_validate(row) for row in rows], total, page, page_size
    )


@router.get(
    "/stats/summary",
    response_model=IncidentStatsSummary,
    summary="Queue counts by band, status and category",
)
def incident_stats(_: OperationalUser, session: DbSession) -> IncidentStatsSummary:
    return IncidentService(session).stats_summary()


@router.get(
    "/stats/priority-agreement",
    response_model=PriorityAgreementSummary,
    summary="How often dispatchers overrule the priority engine",
)
def priority_agreement(
    _: OperationalUser, session: DbSession
) -> PriorityAgreementSummary:
    """The engine's agreement with the humans who can overrule it.

    A rising override rate in one band is the signal that the weights need
    tuning — not a reason for the engine to start tuning itself.
    """
    return IncidentService(session).priority_agreement()


@router.get("/{incident_id}", response_model=IncidentRead, summary="Incident detail")
def read_incident(
    incident_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> IncidentRead:
    """Read one incident.

    A caller who may not see it receives 404 rather than 403, so the API does
    not confirm that the incident exists.
    """
    incident = IncidentService(session).get_for_user(incident_id, user)
    return IncidentRead.model_validate(incident)


@router.patch(
    "/{incident_id}", response_model=IncidentRead, summary="Correct incident facts"
)
def update_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdate,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> IncidentRead:
    incident = IncidentService(session).update_facts(
        incident_id, payload, actor=user, context=context
    )
    return IncidentRead.model_validate(
        IncidentService(session).get_for_user(incident.id, user)
    )


@router.post(
    "/{incident_id}/status", response_model=IncidentRead, summary="Change status"
)
def change_status(
    incident_id: uuid.UUID,
    payload: IncidentStatusChange,
    user: CurrentUser,
    session: DbSession,
    context: Context,
) -> IncidentRead:
    """Move an incident through its lifecycle.

    Dispatchers may make any legal transition; the reporting citizen may only
    cancel their own report, and only before a response is under way.
    """
    service = IncidentService(session)
    incident = service.change_status(incident_id, payload, actor=user, context=context)
    return IncidentRead.model_validate(service.get_for_user(incident.id, user))


@router.post(
    "/{incident_id}/priority",
    response_model=IncidentRead,
    summary="Recompute or override priority",
)
def update_priority(
    incident_id: uuid.UUID,
    payload: IncidentPriorityUpdate,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> IncidentRead:
    service = IncidentService(session)
    incident = service.update_priority(incident_id, payload, actor=user, context=context)
    return IncidentRead.model_validate(service.get_for_user(incident.id, user))


@router.post(
    "/{incident_id}/assign", response_model=IncidentRead, summary="Assign an operator"
)
def assign_incident(
    incident_id: uuid.UUID,
    payload: IncidentAssign,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> IncidentRead:
    service = IncidentService(session)
    incident = service.assign(incident_id, payload, actor=user, context=context)
    return IncidentRead.model_validate(service.get_for_user(incident.id, user))


@router.get(
    "/{incident_id}/history",
    response_model=list[IncidentStatusHistoryRead],
    summary="Status history",
)
def incident_history(
    incident_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> list[IncidentStatusHistoryRead]:
    rows = IncidentService(session).list_history(incident_id, user)
    return [IncidentStatusHistoryRead.model_validate(row) for row in rows]
