"""add the resource inventory

Revision ID: 0005_resources
Revises: 0004_priority_version
Create Date: 2026-09-19 00:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_resources"
down_revision: str | None = "0004_priority_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESOURCE_TYPE_ENUM = postgresql.ENUM(
    "AMBULANCE",
    "FIRE_ENGINE",
    "RESCUE_TEAM",
    "POLICE_UNIT",
    "RESCUE_BOAT",
    "SHELTER",
    "OTHER_RESOURCE",
    name="resource_type",
    create_type=False,
)
RESOURCE_STATUS_ENUM = postgresql.ENUM(
    "AVAILABLE",
    "DISPATCHED",
    "EN_ROUTE",
    "ON_SCENE",
    "OUT_OF_SERVICE",
    name="resource_status",
    create_type=False,
)

_NEW_ENUM_TYPES = (RESOURCE_TYPE_ENUM, RESOURCE_STATUS_ENUM)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _NEW_ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "resources",
        sa.Column("call_sign", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("resource_type", RESOURCE_TYPE_ENUM, nullable=False),
        sa.Column("status", RESOURCE_STATUS_ENUM, nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geography(
                geometry_type="POINT", srid=4326, spatial_index=False, from_text="ST_GeogFromText", name="geography"
            ),
            nullable=False,
        ),
        sa.Column("base_address", sa.String(length=400), nullable=True),
        sa.Column(
            "capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("crew_size", sa.Integer(), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("operator_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
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
            "latitude >= -90 AND latitude <= 90",
            name=op.f("ck_resources_latitude_range"),
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name=op.f("ck_resources_longitude_range"),
        ),
        sa.CheckConstraint(
            "crew_size IS NULL OR crew_size >= 0",
            name=op.f("ck_resources_crew_size_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["users.id"],
            name=op.f("fk_resources_operator_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resources")),
    )
    op.create_index(
        op.f("ix_resources_call_sign"), "resources", ["call_sign"], unique=True
    )
    op.create_index(
        op.f("ix_resources_resource_type"), "resources", ["resource_type"], unique=False
    )
    op.create_index(op.f("ix_resources_status"), "resources", ["status"], unique=False)
    op.create_index(
        op.f("ix_resources_operator_id"), "resources", ["operator_id"], unique=False
    )
    op.create_index(
        "ix_resources_type_status", "resources", ["resource_type", "status"], unique=False
    )
    op.create_index(
        "ix_resources_geom", "resources", ["geom"], unique=False, postgresql_using="gist"
    )


def downgrade() -> None:
    op.drop_index("ix_resources_geom", table_name="resources", postgresql_using="gist")
    op.drop_index("ix_resources_type_status", table_name="resources")
    op.drop_index(op.f("ix_resources_operator_id"), table_name="resources")
    op.drop_index(op.f("ix_resources_status"), table_name="resources")
    op.drop_index(op.f("ix_resources_resource_type"), table_name="resources")
    op.drop_index(op.f("ix_resources_call_sign"), table_name="resources")
    op.drop_table("resources")

    bind = op.get_bind()
    for enum_type in reversed(_NEW_ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)
