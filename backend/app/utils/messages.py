"""Plain-language text for the people this platform writes to.

Kept out of the services so the wording of a message to a frightened citizen
is reviewable in one place, rather than scattered through business logic.
"""

from __future__ import annotations

from app.models.enums import IncidentStatus

_CITIZEN_STATUS_MESSAGES: dict[IncidentStatus, str] = {
    IncidentStatus.REPORTED: "Your report has been received and is waiting to be reviewed.",
    IncidentStatus.RECEIVED: "The control centre has your report.",
    IncidentStatus.UNDER_REVIEW: "An operator is reviewing your report now.",
    IncidentStatus.PRIORITIZED: "Your report has been prioritised and is awaiting assignment.",
    IncidentStatus.ASSIGNED: "A response team has been assigned to your report.",
    IncidentStatus.RESPONDER_EN_ROUTE: "A response team is on the way.",
    IncidentStatus.ON_SCENE: "The response team has arrived at the location.",
    IncidentStatus.RESOLVED: "The incident has been resolved.",
    IncidentStatus.CLOSED: "This report is now closed.",
    IncidentStatus.CANCELLED: "This report was cancelled.",
    IncidentStatus.DUPLICATE: "This was recorded as a duplicate of another report.",
    IncidentStatus.REJECTED: "This report was not accepted by the control centre.",
}


def citizen_status_message(status: IncidentStatus) -> str:
    return _CITIZEN_STATUS_MESSAGES.get(status, f"Your report is now {status.value}.")
