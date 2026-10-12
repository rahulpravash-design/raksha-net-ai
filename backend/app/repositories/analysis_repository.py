"""Persistence for AI-derived incident analyses."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.analysis import IncidentAnalysis


class AnalysisRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, analysis: IncidentAnalysis) -> IncidentAnalysis:
        self.session.add(analysis)
        self.session.flush()
        return analysis

    def get(self, analysis_id: uuid.UUID) -> IncidentAnalysis | None:
        stmt = (
            select(IncidentAnalysis)
            .where(IncidentAnalysis.id == analysis_id)
            .options(joinedload(IncidentAnalysis.reviewed_by))
        )
        return self.session.scalars(stmt).first()

    def list_for_incident(self, incident_id: uuid.UUID) -> list[IncidentAnalysis]:
        stmt = (
            select(IncidentAnalysis)
            .where(IncidentAnalysis.incident_id == incident_id)
            .options(joinedload(IncidentAnalysis.reviewed_by))
            .order_by(IncidentAnalysis.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())
