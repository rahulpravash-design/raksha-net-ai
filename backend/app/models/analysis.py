"""AI-derived incident analysis: a proposal, kept apart from verified facts.

``CLAUDE.md`` section 2, rule 2: AI output is labelled as AI-derived and stored
separately from human-verified facts (``incident_analyses`` vs ``incidents``).
A row here is never a fact until a dispatcher accepts or edits it, and that
happens through the same audited, priority-recalculating path as any other
fact correction (:meth:`app.services.incident_service.IncidentService.update_facts`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AnalysisReviewDecision, IncidentCategory, SeverityLevel
from app.models.incident import Incident
from app.models.user import User


class IncidentAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One AI proposal for one incident.

    An incident may be analysed more than once; each attempt is its own row,
    so a review history is never overwritten.
    """

    __tablename__ = "incident_analyses"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # -- traceability (CLAUDE.md section 2, rule 3) --------------------------
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    processing_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # -- the proposal itself, never applied to the incident on its own -------
    proposed_category: Mapped[IncidentCategory | None] = mapped_column(
        Enum(
            IncidentCategory,
            name="incident_category",
            native_enum=True,
            create_type=False,
        ),
        nullable=True,
    )
    type_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposed_severity: Mapped[SeverityLevel | None] = mapped_column(
        Enum(
            SeverityLevel,
            name="severity_level",
            native_enum=True,
            create_type=False,
        ),
        nullable=True,
    )
    severity_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    people_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    people_trapped: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    medical_support_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    immediate_rescue_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    entities: Mapped[dict[str, list[str]]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    observations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    reasoning_factors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # -- human review (CLAUDE.md section 2, rule 1: AI proposes, a human decides) --
    review_decision: Mapped[AnalysisReviewDecision | None] = mapped_column(
        Enum(AnalysisReviewDecision, name="analysis_review_decision", native_enum=True),
        nullable=True,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: The exact field/value pairs that were written to the incident on
    #: review, if any. Kept here so the audit trail does not have to be
    #: reconstructed from a separate incident.updated entry.
    applied_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    incident: Mapped[Incident] = relationship()
    reviewed_by: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "type_confidence IS NULL OR (type_confidence >= 0 AND type_confidence <= 1)",
            name="type_confidence_range",
        ),
        CheckConstraint(
            "severity_confidence IS NULL OR "
            "(severity_confidence >= 0 AND severity_confidence <= 1)",
            name="severity_confidence_range",
        ),
        Index("ix_incident_analyses_incident_created", "incident_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<IncidentAnalysis {self.id} {self.model_name} {self.review_decision}>"
