"""Analytics response shapes.

Every location value here is a coarsened grid cell, never a raw incident
coordinate (``CLAUDE.md`` section 5). See ``HotspotCell``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import IncidentCategory, ResourceType


class TimeStats(BaseModel):
    """Minutes-based statistics over a set of paired timestamps.

    Used for both response time (report to first dispatch) and resolution
    time (report to resolved). ``sample_size`` is zero when no matching pair
    exists yet, and every other field is ``None`` in that case rather than
    zero, so an empty period does not read as an instant response.
    """

    sample_size: int
    avg_minutes: float | None = None
    median_minutes: float | None = None
    min_minutes: float | None = None
    max_minutes: float | None = None


class CategoryBreakdownItem(BaseModel):
    category: IncidentCategory
    count: int
    avg_priority_score: float | None = None


class CategoryBreakdown(BaseModel):
    items: list[CategoryBreakdownItem] = Field(default_factory=list)
    total: int


class ResourceUtilizationItem(BaseModel):
    resource_type: ResourceType
    total_resources: int
    available_now: int
    dispatches_in_period: int
    avg_dispatches_per_resource: float


class ResourceUtilization(BaseModel):
    items: list[ResourceUtilizationItem] = Field(default_factory=list)
    period_start: datetime | None = None
    period_end: datetime | None = None


class HotspotCell(BaseModel):
    """One grid cell and how many incidents fell inside it.

    ``latitude``/``longitude`` are the cell's rounded centre, snapped to
    ``Hotspots.cell_size_degrees`` — never a reported incident's actual
    position. This is the coarsening ``CLAUDE.md`` section 5 requires of any
    analytics surface.
    """

    latitude: float
    longitude: float
    incident_count: int


class Hotspots(BaseModel):
    cell_size_degrees: float
    items: list[HotspotCell] = Field(default_factory=list)
