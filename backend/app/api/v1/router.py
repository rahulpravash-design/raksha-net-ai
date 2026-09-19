"""Aggregates every v1 route."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyses,
    auth,
    geo,
    health,
    incidents,
    media,
    resources,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(incidents.router)
api_router.include_router(media.router)
api_router.include_router(analyses.router)
api_router.include_router(resources.router)
api_router.include_router(resources.recommendations_router)
api_router.include_router(geo.router)
