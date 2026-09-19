"""add dispatches, with human approval enforced by the schema

Revision ID: 0006_dispatches
Revises: 0005_resources
Create Date: 2026-09-19 00:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_dispatches"
down_revision: str | None = "0005_resources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISPATCH_STATUS_ENUM = postgresql.ENUM(
    "DISPATCHED",
    "ACKNOWLEDGED",
    "EN_ROUTE",
    "ON_SCENE",
    "COMPLETED",
    "CANCELLED",
    name="dispatch_status",
    create_type=False,
)

_NEW_ENUM_TYPES = (DISPATCH_STATUS_ENUM,)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _NEW_ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "dispatches",
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        # NOT NULL is the point of this column: there is no schema-legal way to
        # record a dispatch that no human approved (docs/ROADMAP.md, Phase 11).
        sa.Column("approved_by_id", sa.UUID(), nullable=False),
        sa.Column("status", DISPATCH_STATUS_ENUM, nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("en_route_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("on_scene_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "distance_km IS NULL OR distance_km >= 0",
            name=op.f("ck_dispatches_distance_non_negative"),
        ),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes >= 0",
            name=op.f("ck_dispatches_eta_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_dispatches_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_dispatches_resource_id_resources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
            name=op.f("fk_dispatches_approved_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dispatches")),
    )
    op.create_index(
        op.f("ix_dispatches_incident_id"), "dispatches", ["incident_id"], unique=False
    )
    op.create_index(
        op.f("ix_dispatches_resource_id"), "dispatches", ["resource_id"], unique=False
    )
    op.create_index(
        op.f("ix_dispatches_approved_by_id"),
        "dispatches",
        ["approved_by_id"],
        unique=False,
    )
    op.create_index(op.f("ix_dispatches_status"), "dispatches", ["status"], unique=False)
    op.create_index(
        "ix_dispatches_incident_status", "dispatches", ["incident_id", "status"]
    )
    op.create_index(
        "ix_dispatches_resource_status", "dispatches", ["resource_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_dispatches_resource_status", table_name="dispatches")
    op.drop_index("ix_dispatches_incident_status", table_name="dispatches")
    op.drop_index(op.f("ix_dispatches_status"), table_name="dispatches")
    op.drop_index(op.f("ix_dispatches_approved_by_id"), table_name="dispatches")
    op.drop_index(op.f("ix_dispatches_resource_id"), table_name="dispatches")
    op.drop_index(op.f("ix_dispatches_incident_id"), table_name="dispatches")
    op.drop_table("dispatches")

    bind = op.get_bind()
    for enum_type in reversed(_NEW_ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)
