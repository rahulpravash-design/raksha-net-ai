"""Dispatch persistence."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.dispatch import Dispatch
from app.models.enums import CLOSED_DISPATCH_STATUSES, DispatchStatus
from app.models.resource import Resource


class DispatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, dispatch: Dispatch) -> Dispatch:
        self.session.add(dispatch)
        self.session.flush()
        return dispatch

    def get(self, dispatch_id: uuid.UUID) -> Dispatch | None:
        return self.session.get(Dispatch, dispatch_id)

    def list_for_incident(self, incident_id: uuid.UUID) -> list[Dispatch]:
        stmt = (
            select(Dispatch)
            .where(Dispatch.incident_id == incident_id)
            .order_by(Dispatch.created_at.desc())
        )
        return list(self.session.scalars(stmt).unique().all())

    def active_for_resource(self, resource_id: uuid.UUID) -> Dispatch | None:
        """The open dispatch a unit is already committed to, if any."""
        stmt = select(Dispatch).where(
            Dispatch.resource_id == resource_id,
            Dispatch.status.notin_(list(CLOSED_DISPATCH_STATUSES)),
        )
        return self.session.scalars(stmt).unique().first()

    def list_for_operator(
        self, operator_id: uuid.UUID, *, open_only: bool = True
    ) -> list[Dispatch]:
        """Assignments belonging to the units this responder operates."""
        stmt: Select[tuple[Dispatch]] = (
            select(Dispatch)
            .join(Resource, Resource.id == Dispatch.resource_id)
            .where(Resource.operator_id == operator_id)
        )
        if open_only:
            stmt = stmt.where(Dispatch.status.notin_(list(CLOSED_DISPATCH_STATUSES)))
        stmt = stmt.order_by(Dispatch.created_at.desc())
        return list(self.session.scalars(stmt).unique().all())

    def search(
        self,
        *,
        offset: int,
        limit: int,
        statuses: Sequence[DispatchStatus] | None = None,
        open_only: bool = False,
    ) -> tuple[list[Dispatch], int]:
        stmt: Select[tuple[Dispatch]] = select(Dispatch)
        if statuses:
            stmt = stmt.where(Dispatch.status.in_(list(statuses)))
        if open_only:
            stmt = stmt.where(Dispatch.status.notin_(list(CLOSED_DISPATCH_STATUSES)))

        total = int(
            self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = (
            self.session.scalars(
                stmt.order_by(Dispatch.created_at.desc()).offset(offset).limit(limit)
            )
            .unique()
            .all()
        )
        return list(rows), total
