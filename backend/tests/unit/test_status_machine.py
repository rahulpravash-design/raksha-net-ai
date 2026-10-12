"""The incident lifecycle state machine."""

from __future__ import annotations

import itertools

import pytest

from app.core.errors import ForbiddenError, InvalidStatusTransitionError
from app.models.enums import TERMINAL_STATUSES, IncidentStatus, UserRole
from app.services.status_machine import (
    ALLOWED_TRANSITIONS,
    assert_role_may_transition,
    assert_transition_allowed,
    can_transition,
)


def test_every_status_is_covered_by_the_table() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(IncidentStatus)


def test_terminal_statuses_have_no_exits() -> None:
    for status in TERMINAL_STATUSES:
        assert ALLOWED_TRANSITIONS[status] == frozenset()


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IncidentStatus.REPORTED, IncidentStatus.RECEIVED),
        (IncidentStatus.RECEIVED, IncidentStatus.UNDER_REVIEW),
        (IncidentStatus.UNDER_REVIEW, IncidentStatus.PRIORITIZED),
        (IncidentStatus.PRIORITIZED, IncidentStatus.ASSIGNED),
        (IncidentStatus.ASSIGNED, IncidentStatus.RESPONDER_EN_ROUTE),
        (IncidentStatus.RESPONDER_EN_ROUTE, IncidentStatus.ON_SCENE),
        (IncidentStatus.ON_SCENE, IncidentStatus.RESOLVED),
        (IncidentStatus.RESOLVED, IncidentStatus.CLOSED),
    ],
)
def test_the_happy_path_is_walkable(
    current: IncidentStatus, target: IncidentStatus
) -> None:
    assert can_transition(current, target)
    assert_transition_allowed(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IncidentStatus.REPORTED, IncidentStatus.RESOLVED),
        (IncidentStatus.CLOSED, IncidentStatus.ASSIGNED),
        (IncidentStatus.CANCELLED, IncidentStatus.RECEIVED),
        (IncidentStatus.RESOLVED, IncidentStatus.ASSIGNED),
        (IncidentStatus.REPORTED, IncidentStatus.ON_SCENE),
    ],
)
def test_illegal_transitions_are_refused(
    current: IncidentStatus, target: IncidentStatus
) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidStatusTransitionError):
        assert_transition_allowed(current, target)


def test_transition_to_the_same_status_is_refused() -> None:
    with pytest.raises(InvalidStatusTransitionError):
        assert_transition_allowed(IncidentStatus.RECEIVED, IncidentStatus.RECEIVED)


def test_no_status_declares_itself_as_a_target() -> None:
    for status, targets in ALLOWED_TRANSITIONS.items():
        assert status not in targets


def test_every_non_terminal_status_can_reach_a_terminal_one() -> None:
    """A stuck incident would be invisible to every queue and never closed."""
    for start in IncidentStatus:
        if start in TERMINAL_STATUSES:
            continue
        seen: set[IncidentStatus] = set()
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for target in ALLOWED_TRANSITIONS[current]:
                if target not in seen:
                    seen.add(target)
                    frontier.append(target)
        assert seen & TERMINAL_STATUSES, f"{start} cannot reach a terminal status"


# --- role authorisation ------------------------------------------------------
def test_a_dispatcher_may_make_any_legal_transition() -> None:
    for current, targets in ALLOWED_TRANSITIONS.items():
        for target in targets:
            assert_role_may_transition(
                UserRole.DISPATCHER, current=current, target=target, is_owner=False
            )


def test_the_reporter_may_cancel_before_a_response_starts() -> None:
    for current in (
        IncidentStatus.REPORTED,
        IncidentStatus.RECEIVED,
        IncidentStatus.UNDER_REVIEW,
        IncidentStatus.PRIORITIZED,
    ):
        assert_role_may_transition(
            UserRole.CITIZEN,
            current=current,
            target=IncidentStatus.CANCELLED,
            is_owner=True,
        )


def test_the_reporter_may_not_cancel_once_a_crew_is_moving() -> None:
    """Standing a crew down is an operator's decision, not the reporter's."""
    for current in (
        IncidentStatus.ASSIGNED,
        IncidentStatus.RESPONDER_EN_ROUTE,
        IncidentStatus.ON_SCENE,
    ):
        with pytest.raises(ForbiddenError):
            assert_role_may_transition(
                UserRole.CITIZEN,
                current=current,
                target=IncidentStatus.CANCELLED,
                is_owner=True,
            )


@pytest.mark.parametrize(
    "target",
    [s for s in IncidentStatus if s is not IncidentStatus.CANCELLED],
)
def test_the_reporter_may_not_drive_the_lifecycle(target: IncidentStatus) -> None:
    with pytest.raises(ForbiddenError):
        assert_role_may_transition(
            UserRole.CITIZEN,
            current=IncidentStatus.REPORTED,
            target=target,
            is_owner=True,
        )


@pytest.mark.parametrize(
    ("role", "is_owner"),
    list(itertools.product([UserRole.CITIZEN, UserRole.HOSPITAL_OPERATOR], [False])),
)
def test_a_non_owner_without_a_dispatch_role_is_refused(
    role: UserRole, is_owner: bool
) -> None:
    with pytest.raises(ForbiddenError):
        assert_role_may_transition(
            role,
            current=IncidentStatus.REPORTED,
            target=IncidentStatus.CANCELLED,
            is_owner=is_owner,
        )
