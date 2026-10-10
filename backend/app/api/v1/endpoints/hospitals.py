"""Hospital capacity and inbound-patient notice endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    AdminUser,
    Context,
    CurrentUser,
    DbSession,
    DispatchUser,
    IncidentViewer,
    OperationalUser,
)
from app.schemas.common import Page
from app.schemas.hospital import (
    HospitalCapacityUpdate,
    HospitalCreate,
    HospitalRead,
    InboundNoticeCreate,
    InboundNoticeRead,
    InboundNoticeStatusChange,
    NearbyHospitals,
)
from app.services.hospital_service import HospitalService

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.post(
    "",
    response_model=HospitalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a hospital",
)
def create_hospital(
    payload: HospitalCreate,
    user: AdminUser,
    session: DbSession,
    context: Context,
) -> HospitalRead:
    hospital = HospitalService(session).create(payload, actor=user, context=context)
    return HospitalRead.model_validate(hospital)


@router.get("", response_model=Page[HospitalRead], summary="Hospitals")
def list_hospitals(
    user: OperationalUser,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    active_only: bool = True,
) -> Page[HospitalRead]:
    rows, total = HospitalService(session).list_for_user(
        user, offset=(page - 1) * page_size, limit=page_size, active_only=active_only
    )
    return Page.build(
        [HospitalRead.model_validate(row) for row in rows], total, page, page_size
    )


@router.get(
    "/nearby",
    response_model=NearbyHospitals,
    summary="Hospitals that can take a patient now",
)
def hospitals_nearby(
    user: OperationalUser,
    session: DbSession,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=500)] = 20.0,
    accepting_only: bool = True,
    needs_icu: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NearbyHospitals:
    """Nearest first, and only facilities with a free bed unless asked otherwise."""
    items = HospitalService(session).find_nearby(
        user,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        accepting_only=accepting_only,
        needs_icu=needs_icu,
        limit=limit,
    )
    return NearbyHospitals(items=items, count=len(items))


@router.get("/{hospital_id}", response_model=HospitalRead, summary="Hospital detail")
def read_hospital(
    hospital_id: uuid.UUID, user: OperationalUser, session: DbSession
) -> HospitalRead:
    return HospitalRead.model_validate(
        HospitalService(session).get_for_user(hospital_id, user)
    )


@router.post(
    "/{hospital_id}/capacity",
    response_model=HospitalRead,
    summary="Report current capacity",
)
def update_capacity(
    hospital_id: uuid.UUID,
    payload: HospitalCapacityUpdate,
    user: CurrentUser,
    session: DbSession,
    context: Context,
) -> HospitalRead:
    """The hospital's own operator maintains this; a dispatcher may correct it."""
    hospital = HospitalService(session).update_capacity(
        hospital_id, payload, actor=user, context=context
    )
    return HospitalRead.model_validate(hospital)


@router.get(
    "/{hospital_id}/notices",
    response_model=list[InboundNoticeRead],
    summary="Inbound patients for a hospital",
)
def list_hospital_notices(
    hospital_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    open_only: bool = True,
) -> list[InboundNoticeRead]:
    rows = HospitalService(session).list_notices_for_hospital(
        hospital_id, actor=user, open_only=open_only
    )
    return [InboundNoticeRead.model_validate(row) for row in rows]


notices_router = APIRouter(tags=["hospitals"])


@notices_router.post(
    "/incidents/{incident_id}/hospital-notices",
    response_model=InboundNoticeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Tell a hospital what is coming",
)
def create_notice(
    incident_id: uuid.UUID,
    payload: InboundNoticeCreate,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> InboundNoticeRead:
    """Send an inbound-patient notice.

    The notice carries the incident's category and severity, a headcount, an
    ETA, and whatever clinical note the dispatcher writes. It does not carry
    the reporter's identity, contact details or the text of their report.
    """
    notice = HospitalService(session).create_notice(
        incident_id, payload, actor=user, context=context
    )
    return InboundNoticeRead.model_validate(notice)


@notices_router.get(
    "/incidents/{incident_id}/hospital-notices",
    response_model=list[InboundNoticeRead],
    summary="Hospitals notified for an incident",
)
def list_incident_notices(
    incident_id: uuid.UUID, user: IncidentViewer, session: DbSession
) -> list[InboundNoticeRead]:
    rows = HospitalService(session).list_notices_for_incident(incident_id, actor=user)
    return [InboundNoticeRead.model_validate(row) for row in rows]


@notices_router.post(
    "/hospital-notices/{notice_id}/status",
    response_model=InboundNoticeRead,
    summary="Acknowledge, divert or close an inbound notice",
)
def respond_to_notice(
    notice_id: uuid.UUID,
    payload: InboundNoticeStatusChange,
    user: CurrentUser,
    session: DbSession,
    context: Context,
) -> InboundNoticeRead:
    notice = HospitalService(session).respond_to_notice(
        notice_id, payload, actor=user, context=context
    )
    return InboundNoticeRead.model_validate(notice)
