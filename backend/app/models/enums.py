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
