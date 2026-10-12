"""Geospatial read operations exposed to the API."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ValidationError
from app.repositories.incident_repository import IncidentRepository
from app.schemas.geo import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONGeometry,
    NearbyIncident,
    NearbyResponse,
)
from app.utils.geo import validate_bounding_box, validate_coordinates


class GeoService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = IncidentRepository(session)

    def nearby_incidents(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int = 50,
        open_only: bool = True,
    ) -> NearbyResponse:
        coords = validate_coordinates(latitude, longitude, self.settings)

        if radius_km <= 0:
            raise ValidationError("radius_km must be greater than zero.")
        capped = min(radius_km, self.settings.geo_max_search_radius_km)

        rows = self.repo.find_nearby(
            latitude=float(coords.latitude),
            longitude=float(coords.longitude),
            radius_km=capped,
            limit=limit,
            open_only=open_only,
        )
        items = [
            NearbyIncident(**row | {"distance_km": round(row["distance_km"], 3)})
            for row in rows
        ]
        return NearbyResponse(items=items, count=len(items), radius_km=capped)

    def incidents_in_bbox(
        self,
        *,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        limit: int = 500,
        open_only: bool = True,
    ) -> GeoJSONFeatureCollection:
        validate_bounding_box(min_lat, min_lon, max_lat, max_lon)

        rows = self.repo.find_in_bbox(
            min_lat=min_lat,
            min_lon=min_lon,
            max_lat=max_lat,
            max_lon=max_lon,
            limit=limit,
            open_only=open_only,
        )
        features = [
            GeoJSONFeature(
                id=row["id"],
                geometry=GeoJSONGeometry(coordinates=(row["longitude"], row["latitude"])),
                properties={
                    "reference_code": row["reference_code"],
                    "category": row["category"],
                    "status": row["status"],
                    "priority_band": row["priority_band"],
                    "priority_score": row["priority_score"],
                    "people_affected": row["people_affected"],
                    "people_trapped": row["people_trapped"],
                    "created_at": row["created_at"].isoformat(),
                },
            )
            for row in rows
        ]
        return GeoJSONFeatureCollection(
            features=features,
            count=len(features),
            truncated=len(features) >= limit,
        )
