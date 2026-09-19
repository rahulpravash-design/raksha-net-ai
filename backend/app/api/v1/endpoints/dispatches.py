"""Dispatch endpoints: commit a unit, and follow it to the scene."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import Context, CurrentUser, DbSession, DispatchUser, OperationalUser
from app.schemas.dispatch import (
    DispatchCreate,
    DispatchRead,
    DispatchStatusChange,
    ResponderAssignment,
)
from app.services.dispatch_service import DispatchService

router = APIRouter(tags=["dispatch"])


@router.post(
    "/incidents/{incident_id}/dispatches",
    response_model=DispatchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch a resource to an incident",
)
def create_dispatch(
    incident_id: uuid.UUID,
    payload: DispatchCreate,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> DispatchRead:
    """Send a unit.

    The approver recorded on the dispatch is the authenticated dispatcher
    making this call. The request body has no field for it, and the database
    will not accept a dispatch without one.
    """
    dispatch = DispatchService(session).create(
        incident_id, payload, actor=user, context=context
    )
    return DispatchRead.model_validate(dispatch)


@router.get(
    "/incidents/{incident_id}/dispatches",
    response_model=list[DispatchRead],
    summary="Resources sent to an incident",
)
def list_incident_dispatches(
    incident_id: uuid.UUID, user: OperationalUser, session: DbSession
) -> list[DispatchRead]:
    rows = DispatchService(session).list_for_incident(incident_id, actor=user)
    return [DispatchRead.model_validate(row) for row in rows]


@router.get(
    "/dispatches/mine",
    response_model=list[ResponderAssignment],
    summary="The caller's own assignments",
)
def my_assignments(
    user: OperationalUser,
    session: DbSession,
    open_only: Annotated[bool, Query()] = True,
) -> list[ResponderAssignment]:
    """What the responder application shows: this crew's assignments, with the
    scene brief they need — and without the reporter's identity."""
    rows = DispatchService(session).list_my_assignments(user, open_only=open_only)
    return [ResponderAssignment.model_validate(row) for row in rows]


@router.get(
    "/dispatches/{dispatch_id}",
    response_model=ResponderAssignment,
    summary="Dispatch detail",
)
def read_dispatch(
    dispatch_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> ResponderAssignment:
    dispatch = DispatchService(session).get_for_user(dispatch_id, user)
    return ResponderAssignment.model_validate(dispatch)


@router.post(
    "/dispatches/{dispatch_id}/status",
    response_model=ResponderAssignment,
    summary="Update a dispatch's progress",
)
def change_dispatch_status(
    dispatch_id: uuid.UUID,
    payload: DispatchStatusChange,
    user: CurrentUser,
    session: DbSession,
    context: Context,
) -> ResponderAssignment:
    """The crew reports progress; the dispatcher may also move or cancel it."""
    dispatch = DispatchService(session).change_status(
        dispatch_id, payload, actor=user, context=context
    )
    return ResponderAssignment.model_validate(dispatch)
