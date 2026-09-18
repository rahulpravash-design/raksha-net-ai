"""SQLAlchemy models.

Importing this package registers every mapper with :class:`app.db.base.Base`,
which Alembic's autogenerate relies on.
"""

from app.models.enums import (
    ADMIN_ROLES,
    DISPATCH_ROLES,
    OPEN_STATUSES,
    OPERATIONAL_ROLES,
    TERMINAL_STATUSES,
    IncidentCategory,
    IncidentStatus,
    MediaType,
    PriorityBand,
    SeverityLevel,
    UserRole,
)
from app.models.incident import (
    AuditLog,
    Incident,
    IncidentMedia,
    IncidentStatusHistory,
)
from app.models.user import RefreshToken, User

__all__ = [
    "ADMIN_ROLES",
    "DISPATCH_ROLES",
    "OPEN_STATUSES",
    "OPERATIONAL_ROLES",
    "TERMINAL_STATUSES",
    "AuditLog",
    "Incident",
    "IncidentCategory",
    "IncidentMedia",
    "IncidentStatus",
    "IncidentStatusHistory",
    "MediaType",
    "PriorityBand",
    "RefreshToken",
    "SeverityLevel",
    "User",
    "UserRole",
]
