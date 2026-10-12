"""The incident status state machine.

Kept separate from :mod:`app.services.incident_service` so the rules can be
tested without a database, and so there is exactly one place that decides
whether a transition is legal.
"""

from __future__ import annotations

from app.core.errors import ForbiddenError, InvalidStatusTransitionError
from app.models.enums import DISPATCH_ROLES, TERMINAL_STATUSES, IncidentStatus, UserRole

#: Statuses reachable from each status. Terminal statuses map to an empty set.
ALLOWED_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.REPORTED: frozenset(
        {
            IncidentStatus.RECEIVED,
            IncidentStatus.UNDER_REVIEW,
            IncidentStatus.CANCELLED,
            IncidentStatus.DUPLICATE,
            IncidentStatus.REJECTED,
        }
    ),
    IncidentStatus.RECEIVED: frozenset(
        {
            IncidentStatus.UNDER_REVIEW,
            IncidentStatus.PRIORITIZED,
            IncidentStatus.CANCELLED,
            IncidentStatus.DUPLICATE,
            IncidentStatus.REJECTED,
        }
    ),
    IncidentStatus.UNDER_REVIEW: frozenset(
        {
            IncidentStatus.PRIORITIZED,
            IncidentStatus.ASSIGNED,
            IncidentStatus.CANCELLED,
            IncidentStatus.DUPLICATE,
            IncidentStatus.REJECTED,
        }
    ),
    IncidentStatus.PRIORITIZED: frozenset(
        {
            IncidentStatus.ASSIGNED,
            IncidentStatus.UNDER_REVIEW,
            IncidentStatus.CANCELLED,
            IncidentStatus.DUPLICATE,
            IncidentStatus.REJECTED,
        }
    ),
    IncidentStatus.ASSIGNED: frozenset(
        {
            IncidentStatus.RESPONDER_EN_ROUTE,
            IncidentStatus.ON_SCENE,
            IncidentStatus.PRIORITIZED,
            IncidentStatus.RESOLVED,
            IncidentStatus.CANCELLED,
        }
    ),
    IncidentStatus.RESPONDER_EN_ROUTE: frozenset(
        {
            IncidentStatus.ON_SCENE,
            IncidentStatus.RESOLVED,
            IncidentStatus.ASSIGNED,
            IncidentStatus.CANCELLED,
        }
    ),
    IncidentStatus.ON_SCENE: frozenset(
        {IncidentStatus.RESOLVED, IncidentStatus.RESPONDER_EN_ROUTE}
    ),
    IncidentStatus.RESOLVED: frozenset({IncidentStatus.CLOSED, IncidentStatus.ON_SCENE}),
    IncidentStatus.CLOSED: frozenset(),
    IncidentStatus.CANCELLED: frozenset(),
    IncidentStatus.DUPLICATE: frozenset(),
    IncidentStatus.REJECTED: frozenset(),
}

#: The only statuses a reporting citizen may set on their own incident, and only
#: while the incident has not yet been assigned to a responder.
CITIZEN_ALLOWED_TARGETS: frozenset[IncidentStatus] = frozenset({IncidentStatus.CANCELLED})

#: A citizen may no longer withdraw once a response is under way.
CITIZEN_CANCEL_BLOCKED_FROM: frozenset[IncidentStatus] = (
    frozenset(
        {
            IncidentStatus.ASSIGNED,
            IncidentStatus.RESPONDER_EN_ROUTE,
            IncidentStatus.ON_SCENE,
        }
    )
    | TERMINAL_STATUSES
)


def can_transition(current: IncidentStatus, target: IncidentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition_allowed(current: IncidentStatus, target: IncidentStatus) -> None:
    """Raise unless ``current -> target`` is a legal move."""
    if current is target:
        raise InvalidStatusTransitionError(
            f"The incident is already {current.value}.",
            details={"from": current.value, "to": target.value},
        )
    if not can_transition(current, target):
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, frozenset()))
        raise InvalidStatusTransitionError(
            f"Cannot move an incident from {current.value} to {target.value}.",
            details={"from": current.value, "to": target.value, "allowed": allowed},
        )


def assert_role_may_transition(
    role: UserRole,
    *,
    current: IncidentStatus,
    target: IncidentStatus,
    is_owner: bool,
) -> None:
    """Authorise the actor for this specific transition.

    Dispatch roles may make any legal transition. The reporting citizen may only
    withdraw their own report, and only before a response is under way — once a
    crew is moving, standing them down is an operator's decision.
    """
    if role in DISPATCH_ROLES:
        return

    if is_owner and target in CITIZEN_ALLOWED_TARGETS:
        if current in CITIZEN_CANCEL_BLOCKED_FROM:
            raise ForbiddenError(
                "This report can no longer be cancelled because a response is "
                "already under way. Please contact the control centre.",
                details={"current_status": current.value},
            )
        return

    raise ForbiddenError("You do not have permission to change this status.")
