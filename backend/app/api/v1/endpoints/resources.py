"""Resource inventory, status and recommendation endpoints.

Note what is absent: there is no endpoint here that sends a resource anywhere.
Phase 10 recommends; Phase 11's dispatch endpoint is the only thing that
commits a unit, and it records the human who approved it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import Context, CurrentUser, DbSession, DispatchUser, OperationalUser
from app.models.enums import ResourceStatus, ResourceType
from app.schemas.common import Page
from app.schemas.resource import (
    NearbyResources,
    ResourceCreate,
    ResourceRead,
    ResourceRecommendations,
    ResourceStatsSummary,
    ResourceStatusChange,
    ResourceUpdate,
)
from app.services.resource_service import ResourceService

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post(
    "",
    response_model=ResourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a resource",
)
def create_resource(
    payload: ResourceCreate,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> ResourceRead:
    resource = ResourceService(session).create(payload, actor=user, context=context)
    return ResourceRead.model_validate(resource)


@router.get("", response_model=Page[ResourceRead], summary="Resource inventory")
def list_resources(
    user: OperationalUser,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    resource_type: Annotated[list[ResourceType] | None, Query()] = None,
    status_filter: Annotated[list[ResourceStatus] | None, Query(alias="status")] = None,
    active_only: bool = True,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> Page[ResourceRead]:
    rows, total = ResourceService(session).list_for_user(
        user,
        offset=(page - 1) * page_size,
        limit=page_size,
        resource_types=resource_type,
        statuses=status_filter,
        active_only=active_only,
        query=q,
    )
    return Page.build(
        [ResourceRead.model_validate(row) for row in rows], total, page, page_size
    )


@router.get(
    "/stats/summary",
    response_model=ResourceStatsSummary,
    summary="Resource counts by status and type",
)
def resource_stats(user: OperationalUser, session: DbSession) -> ResourceStatsSummary:
    return ResourceService(session).stats(user)


@router.get(
    "/nearby",
    response_model=NearbyResources,
    summary="Resources within a radius of a point",
)
def resources_nearby(
    user: OperationalUser,
    session: DbSession,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=500)] = 10.0,
    resource_type: Annotated[list[ResourceType] | None, Query()] = None,
    available_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NearbyResources:
    """Nearest units first. The radius is capped by the deployment's maximum."""
    items = ResourceService(session).find_nearby(
        user,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        resource_types=resource_type,
        available_only=available_only,
        limit=limit,
    )
    return NearbyResources(items=items, count=len(items))


@router.get("/{resource_id}", response_model=ResourceRead, summary="Resource detail")
def read_resource(
    resource_id: uuid.UUID, user: OperationalUser, session: DbSession
) -> ResourceRead:
    return ResourceRead.model_validate(
        ResourceService(session).get_for_user(resource_id, user)
    )


@router.patch("/{resource_id}", response_model=ResourceRead, summary="Update a resource")
def update_resource(
    resource_id: uuid.UUID,
    payload: ResourceUpdate,
    user: DispatchUser,
    session: DbSession,
    context: Context,
) -> ResourceRead:
    resource = ResourceService(session).update(
        resource_id, payload, actor=user, context=context
    )
    return ResourceRead.model_validate(resource)


@router.post(
    "/{resource_id}/status",
    response_model=ResourceRead,
    summary="Set a resource's operational status",
)
def change_resource_status(
    resource_id: uuid.UUID,
    payload: ResourceStatusChange,
    user: CurrentUser,
    session: DbSession,
    context: Context,
) -> ResourceRead:
    """A dispatcher may set any unit's status; a responder only their own unit's."""
    resource = ResourceService(session).change_status(
        resource_id, payload, actor=user, context=context
    )
    return ResourceRead.model_validate(resource)


recommendations_router = APIRouter(prefix="/incidents", tags=["resources"])


@recommendations_router.get(
    "/{incident_id}/resource-recommendations",
    response_model=ResourceRecommendations,
    summary="Ranked resource suggestions for an incident",
)
def recommend_resources(
    incident_id: uuid.UUID,
    user: OperationalUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> ResourceRecommendations:
    """Suggestions, with the reasons behind each ranking.

    Nothing here dispatches. The dispatcher reads the reasons, disagrees where
    they know better, and sends whichever unit they choose.
    """
    return ResourceService(session).recommend_for_incident(
        incident_id, actor=user, limit=limit
    )
