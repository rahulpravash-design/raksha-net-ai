"""Geospatial query and response schemas."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import IncidentCategory, IncidentStatus, PriorityBand


class NearbyIncident(BaseModel):
    id: uuid.UUID
    reference_code: str
    category: IncidentCategory
    status: IncidentStatus
    priority_band: PriorityBand | None
    priority_score: int | None
    latitude: float
    longitude: float
    distance_km: float = Field(description="Geodesic distance from the query point.")


class NearbyResponse(BaseModel):
    items: list[NearbyIncident]
    count: int
    radius_km: float


class GeoJSONGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float] = Field(description="[longitude, latitude]")


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: uuid.UUID
    geometry: GeoJSONGeometry
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]
    count: int
    truncated: bool = Field(
        default=False,
        description="True when the viewport held more incidents than the limit.",
    )
