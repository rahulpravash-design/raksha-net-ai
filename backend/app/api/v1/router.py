"""Aggregates every v1 route."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyses,
    analytics,
    auth,
    dispatches,
    geo,
    health,
    hospitals,
    incidents,
    media,
    notifications,
    resources,
    transcriptions,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(incidents.router)
api_router.include_router(media.router)
api_router.include_router(analyses.router)
api_router.include_router(transcriptions.router)
api_router.include_router(resources.router)
api_router.include_router(resources.recommendations_router)
api_router.include_router(dispatches.router)
api_router.include_router(hospitals.router)
api_router.include_router(hospitals.notices_router)
api_router.include_router(notifications.router)
api_router.include_router(analytics.router)
api_router.include_router(geo.router)
