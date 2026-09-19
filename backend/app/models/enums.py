"""Domain enumerations.

These are mirrored as PostgreSQL ``ENUM`` types so the database rejects an
invalid value even if application code is bypassed.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CITIZEN = "CITIZEN"
    RESPONDER = "RESPONDER"
    DISPATCHER = "DISPATCHER"
    HOSPITAL_OPERATOR = "HOSPITAL_OPERATOR"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


#: Roles that may see the full incident picture rather than only their own reports.
OPERATIONAL_ROLES: frozenset[UserRole] = frozenset(
    {
        UserRole.RESPONDER,
        UserRole.DISPATCHER,
        UserRole.HOSPITAL_OPERATOR,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    }
)

#: Roles that may change an incident's status, priority or assignment.
DISPATCH_ROLES: frozenset[UserRole] = frozenset(
    {UserRole.DISPATCHER, UserRole.ADMIN, UserRole.SUPER_ADMIN}
)

#: Roles that may administer users.
ADMIN_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN, UserRole.SUPER_ADMIN})


class IncidentCategory(StrEnum):
    FLOOD = "FLOOD"
    FIRE = "FIRE"
    ROAD_ACCIDENT = "ROAD_ACCIDENT"
    MEDICAL = "MEDICAL"
    BUILDING_COLLAPSE = "BUILDING_COLLAPSE"
    MISSING_PERSON = "MISSING_PERSON"
    LANDSLIDE = "LANDSLIDE"
    INDUSTRIAL_ACCIDENT = "INDUSTRIAL_ACCIDENT"
    GAS_LEAK = "GAS_LEAK"
    ELECTRICAL_HAZARD = "ELECTRICAL_HAZARD"
    OTHER = "OTHER"


class IncidentStatus(StrEnum):
    REPORTED = "REPORTED"
    RECEIVED = "RECEIVED"
    UNDER_REVIEW = "UNDER_REVIEW"
    PRIORITIZED = "PRIORITIZED"
    ASSIGNED = "ASSIGNED"
    RESPONDER_EN_ROUTE = "RESPONDER_EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"


#: Statuses from which no further transition is possible.
TERMINAL_STATUSES: frozenset[IncidentStatus] = frozenset(
    {
        IncidentStatus.CLOSED,
        IncidentStatus.CANCELLED,
        IncidentStatus.DUPLICATE,
        IncidentStatus.REJECTED,
    }
)

#: Statuses that represent an incident still needing attention.
OPEN_STATUSES: frozenset[IncidentStatus] = frozenset(
    {
        IncidentStatus.REPORTED,
        IncidentStatus.RECEIVED,
        IncidentStatus.UNDER_REVIEW,
        IncidentStatus.PRIORITIZED,
        IncidentStatus.ASSIGNED,
        IncidentStatus.RESPONDER_EN_ROUTE,
        IncidentStatus.ON_SCENE,
    }
)


class SeverityLevel(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class PriorityBand(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MediaType(StrEnum):
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"


class ResourceType(StrEnum):
    AMBULANCE = "AMBULANCE"
    FIRE_ENGINE = "FIRE_ENGINE"
    RESCUE_TEAM = "RESCUE_TEAM"
    POLICE_UNIT = "POLICE_UNIT"
    RESCUE_BOAT = "RESCUE_BOAT"
    SHELTER = "SHELTER"
    OTHER_RESOURCE = "OTHER_RESOURCE"


class ResourceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE = "EN_ROUTE"
    ON_SCENE = "ON_SCENE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


#: A resource in one of these states cannot be recommended or dispatched.
UNAVAILABLE_RESOURCE_STATUSES: frozenset[ResourceStatus] = frozenset(
    {
        ResourceStatus.DISPATCHED,
        ResourceStatus.EN_ROUTE,
        ResourceStatus.ON_SCENE,
        ResourceStatus.OUT_OF_SERVICE,
    }
)

#: Which kinds of unit a category usually needs, best match first. Used only to
#: rank recommendations for a human to choose from — never to dispatch
#: (``CLAUDE.md`` section 2, rule 1).
CATEGORY_RESOURCE_PREFERENCE: dict[IncidentCategory, tuple[ResourceType, ...]] = {
    IncidentCategory.MEDICAL: (ResourceType.AMBULANCE, ResourceType.RESCUE_TEAM),
    IncidentCategory.FIRE: (
        ResourceType.FIRE_ENGINE,
        ResourceType.AMBULANCE,
        ResourceType.RESCUE_TEAM,
    ),
    IncidentCategory.FLOOD: (
        ResourceType.RESCUE_BOAT,
        ResourceType.RESCUE_TEAM,
        ResourceType.AMBULANCE,
    ),
    IncidentCategory.ROAD_ACCIDENT: (
        ResourceType.AMBULANCE,
        ResourceType.POLICE_UNIT,
        ResourceType.FIRE_ENGINE,
    ),
    IncidentCategory.BUILDING_COLLAPSE: (
        ResourceType.RESCUE_TEAM,
        ResourceType.AMBULANCE,
        ResourceType.FIRE_ENGINE,
    ),
    IncidentCategory.LANDSLIDE: (ResourceType.RESCUE_TEAM, ResourceType.AMBULANCE),
    IncidentCategory.GAS_LEAK: (ResourceType.FIRE_ENGINE, ResourceType.RESCUE_TEAM),
    IncidentCategory.INDUSTRIAL_ACCIDENT: (
        ResourceType.FIRE_ENGINE,
        ResourceType.AMBULANCE,
        ResourceType.RESCUE_TEAM,
    ),
    IncidentCategory.ELECTRICAL_HAZARD: (
        ResourceType.FIRE_ENGINE,
        ResourceType.RESCUE_TEAM,
    ),
    IncidentCategory.MISSING_PERSON: (
        ResourceType.POLICE_UNIT,
        ResourceType.RESCUE_TEAM,
    ),
    IncidentCategory.OTHER: (),
}


class AnalysisReviewDecision(StrEnum):
    """A dispatcher's disposition of one AI proposal.

    There is no "pending" member: a row with ``review_decision IS NULL`` is
    pending. That keeps "has this been reviewed" a single null check rather
    than a value comparison that can drift out of sync with it.
    """

    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"
