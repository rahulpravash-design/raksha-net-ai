"""add hospitals and inbound patient notices

Revision ID: 0007_hospitals
Revises: 0006_dispatches
Create Date: 2026-09-19 00:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_hospitals"
down_revision: str | None = "0006_dispatches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INCIDENT_CATEGORY_ENUM = postgresql.ENUM(name="incident_category", create_type=False)
SEVERITY_LEVEL_ENUM = postgresql.ENUM(name="severity_level", create_type=False)
NOTICE_STATUS_ENUM = postgresql.ENUM(
    "NOTIFIED",
    "ACKNOWLEDGED",
    "ARRIVED",
    "DIVERTED",
    "CANCELLED",
    name="hospital_notice_status",
    create_type=False,
)

_NEW_ENUM_TYPES = (NOTICE_STATUS_ENUM,)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _NEW_ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "hospitals",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=False,
        ),
        sa.Column("address", sa.String(length=400), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("total_beds", sa.Integer(), nullable=False),
        sa.Column("available_beds", sa.Integer(), nullable=False),
        sa.Column("icu_total", sa.Integer(), nullable=False),
        sa.Column("icu_available", sa.Integer(), nullable=False),
        sa.Column("accepting_emergencies", sa.Boolean(), nullable=False),
        sa.Column(
            "specialties", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("managed_by_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("capacity_updated_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("ck_hospitals_latitude_range"),
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name=op.f("ck_hospitals_longitude_range"),
        ),
        sa.CheckConstraint(
            "available_beds >= 0 AND available_beds <= total_beds",
            name=op.f("ck_hospitals_available_beds_within_total"),
        ),
        sa.CheckConstraint(
            "icu_available >= 0 AND icu_available <= icu_total",
            name=op.f("ck_hospitals_icu_available_within_total"),
        ),
        sa.ForeignKeyConstraint(
            ["managed_by_id"],
            ["users.id"],
            name=op.f("fk_hospitals_managed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospitals")),
    )
    op.create_index(op.f("ix_hospitals_code"), "hospitals", ["code"], unique=True)
    op.create_index(
        op.f("ix_hospitals_managed_by_id"), "hospitals", ["managed_by_id"], unique=False
    )
    op.create_index(
        "ix_hospitals_geom", "hospitals", ["geom"], unique=False, postgresql_using="gist"
    )

    op.create_table(
        "inbound_patient_notices",
        sa.Column("hospital_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("dispatch_id", sa.UUID(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("status", NOTICE_STATUS_ENUM, nullable=False),
        sa.Column("patient_count", sa.Integer(), nullable=False),
        sa.Column("category", INCIDENT_CATEGORY_ENUM, nullable=False),
        sa.Column("severity", SEVERITY_LEVEL_ENUM, nullable=True),
        sa.Column("eta_minutes", sa.Integer(), nullable=True),
        sa.Column("clinical_notes", sa.String(length=1000), nullable=True),
        sa.Column("response_note", sa.String(length=1000), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
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
            "patient_count >= 1",
            name=op.f("ck_inbound_patient_notices_patient_count_positive"),
        ),
        sa.CheckConstraint(
            "eta_minutes IS NULL OR eta_minutes >= 0",
            name=op.f("ck_inbound_patient_notices_eta_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["hospital_id"],
            ["hospitals.id"],
            name=op.f("fk_inbound_patient_notices_hospital_id_hospitals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_inbound_patient_notices_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dispatch_id"],
            ["dispatches.id"],
            name=op.f("fk_inbound_patient_notices_dispatch_id_dispatches"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_inbound_patient_notices_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbound_patient_notices")),
    )
    op.create_index(
        op.f("ix_inbound_patient_notices_hospital_id"),
        "inbound_patient_notices",
        ["hospital_id"],
    )
    op.create_index(
        op.f("ix_inbound_patient_notices_incident_id"),
        "inbound_patient_notices",
        ["incident_id"],
    )
    op.create_index(
        op.f("ix_inbound_patient_notices_status"), "inbound_patient_notices", ["status"]
    )
    op.create_index(
        "ix_notices_hospital_status",
        "inbound_patient_notices",
        ["hospital_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_notices_hospital_status", table_name="inbound_patient_notices")
    op.drop_index(
        op.f("ix_inbound_patient_notices_status"), table_name="inbound_patient_notices"
    )
    op.drop_index(
        op.f("ix_inbound_patient_notices_incident_id"),
        table_name="inbound_patient_notices",
    )
    op.drop_index(
        op.f("ix_inbound_patient_notices_hospital_id"),
        table_name="inbound_patient_notices",
    )
    op.drop_table("inbound_patient_notices")

    op.drop_index("ix_hospitals_geom", table_name="hospitals", postgresql_using="gist")
    op.drop_index(op.f("ix_hospitals_managed_by_id"), table_name="hospitals")
    op.drop_index(op.f("ix_hospitals_code"), table_name="hospitals")
    op.drop_table("hospitals")

    bind = op.get_bind()
    for enum_type in reversed(_NEW_ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)
