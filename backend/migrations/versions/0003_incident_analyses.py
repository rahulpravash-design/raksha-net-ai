"""add incident analyses

Revision ID: 0003_incident_analyses
Revises: 0002_core_schema
Create Date: 2026-09-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_incident_analyses"
down_revision: str | None = "0002_core_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``incident_category`` and ``severity_level`` already exist (created in
# 0002); they are referenced here, not created again. ``analysis_review_decision``
# is new to this migration and is created explicitly, for the same reason the
# other enum types are: Postgres does not drop a type with its table, so an
# implicit create-on-first-column-use would make this migration non-repeatable
# after a downgrade.
INCIDENT_CATEGORY_ENUM = postgresql.ENUM(
    "FLOOD",
    "FIRE",
    "ROAD_ACCIDENT",
    "MEDICAL",
    "BUILDING_COLLAPSE",
    "MISSING_PERSON",
    "LANDSLIDE",
    "INDUSTRIAL_ACCIDENT",
    "GAS_LEAK",
    "ELECTRICAL_HAZARD",
    "OTHER",
    name="incident_category",
    create_type=False,
)
SEVERITY_LEVEL_ENUM = postgresql.ENUM(
    "CRITICAL",
    "HIGH",
    "MODERATE",
    "LOW",
    name="severity_level",
    create_type=False,
)
ANALYSIS_REVIEW_DECISION_ENUM = postgresql.ENUM(
    "ACCEPTED",
    "EDITED",
    "REJECTED",
    name="analysis_review_decision",
    create_type=False,
)

_NEW_ENUM_TYPES = (ANALYSIS_REVIEW_DECISION_ENUM,)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _NEW_ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "incident_analyses",
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("proposed_category", INCIDENT_CATEGORY_ENUM, nullable=True),
        sa.Column("type_confidence", sa.Float(), nullable=True),
        sa.Column("proposed_severity", SEVERITY_LEVEL_ENUM, nullable=True),
        sa.Column("severity_confidence", sa.Float(), nullable=True),
        sa.Column("people_affected", sa.Integer(), nullable=True),
        sa.Column("people_trapped", sa.Boolean(), nullable=True),
        sa.Column("medical_support_required", sa.Boolean(), nullable=True),
        sa.Column("immediate_rescue_required", sa.Boolean(), nullable=True),
        sa.Column(
            "entities", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "observations", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "reasoning_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("review_decision", ANALYSIS_REVIEW_DECISION_ENUM, nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=1000), nullable=True),
        sa.Column(
            "applied_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type_confidence IS NULL OR (type_confidence >= 0 AND type_confidence <= 1)",
            name=op.f("ck_incident_analyses_type_confidence_range"),
        ),
        sa.CheckConstraint(
            "severity_confidence IS NULL OR "
            "(severity_confidence >= 0 AND severity_confidence <= 1)",
            name=op.f("ck_incident_analyses_severity_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_analyses_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_incident_analyses_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_analyses")),
    )
    op.create_index(
        op.f("ix_incident_analyses_incident_id"),
        "incident_analyses",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_incident_analyses_incident_created",
        "incident_analyses",
        ["incident_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_incident_analyses_incident_created", table_name="incident_analyses"
    )
    op.drop_index(
        op.f("ix_incident_analyses_incident_id"), table_name="incident_analyses"
    )
    op.drop_table("incident_analyses")

    bind = op.get_bind()
    for enum_type in reversed(_NEW_ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)
