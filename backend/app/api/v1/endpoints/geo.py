"""Geospatial query endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AppSettings, DbSession, IncidentViewer
from app.schemas.geo import GeoJSONFeatureCollection, NearbyResponse
from app.services.geo_service import GeoService

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get(
    "/incidents/nearby",
    response_model=NearbyResponse,
    summary="Incidents within a radius",
)
def incidents_nearby(
    _: IncidentViewer,
    session: DbSession,
    settings: AppSettings,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=500)] = 5.0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    open_only: bool = True,
) -> NearbyResponse:
    """Find incidents near a point, most urgent then nearest first.

    ``radius_km`` is capped by ``RAKSHA_GEO_MAX_SEARCH_RADIUS_KM``; the response
    reports the radius actually used.
    """
    return GeoService(session, settings).nearby_incidents(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        limit=limit,
        open_only=open_only,
    )


@router.get(
    "/incidents/bbox",
    response_model=GeoJSONFeatureCollection,
    summary="Incidents in a map viewport (GeoJSON)",
)
def incidents_in_bbox(
    _: IncidentViewer,
    session: DbSession,
    settings: AppSettings,
    min_lat: Annotated[float, Query(ge=-90, le=90)],
    min_lon: Annotated[float, Query(ge=-180, le=180)],
    max_lat: Annotated[float, Query(ge=-90, le=90)],
    max_lon: Annotated[float, Query(ge=-180, le=180)],
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    open_only: bool = True,
) -> GeoJSONFeatureCollection:
    return GeoService(session, settings).incidents_in_bbox(
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
        limit=limit,
        open_only=open_only,
    )
