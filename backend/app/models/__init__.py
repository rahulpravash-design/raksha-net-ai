"""SQLAlchemy models.

Importing this package registers every mapper with :class:`app.db.base.Base`,
which Alembic's autogenerate relies on.
"""

from app.models.analysis import IncidentAnalysis
from app.models.dispatch import Dispatch
from app.models.enums import (
    ADMIN_ROLES,
    DISPATCH_ROLES,
    OPEN_STATUSES,
    OPERATIONAL_ROLES,
    TERMINAL_STATUSES,
    AnalysisReviewDecision,
    DispatchStatus,
    HospitalNoticeStatus,
    IncidentCategory,
    IncidentStatus,
    MediaType,
    PriorityBand,
    ResourceStatus,
    ResourceType,
    SeverityLevel,
    UserRole,
)
from app.models.hospital import Hospital, InboundPatientNotice
from app.models.incident import (
    AuditLog,
    Incident,
    IncidentMedia,
    IncidentStatusHistory,
)
from app.models.resource import Resource
from app.models.user import RefreshToken, User

__all__ = [
    "ADMIN_ROLES",
    "DISPATCH_ROLES",
    "OPEN_STATUSES",
    "OPERATIONAL_ROLES",
    "TERMINAL_STATUSES",
    "AnalysisReviewDecision",
    "AuditLog",
    "Dispatch",
    "DispatchStatus",
    "Hospital",
    "HospitalNoticeStatus",
    "InboundPatientNotice",
    "Incident",
    "IncidentAnalysis",
    "IncidentCategory",
    "IncidentMedia",
    "IncidentStatus",
    "IncidentStatusHistory",
    "MediaType",
    "PriorityBand",
    "RefreshToken",
    "Resource",
    "ResourceStatus",
    "ResourceType",
    "SeverityLevel",
    "User",
    "UserRole",
]
