"""add notifications and per-channel delivery records

Revision ID: 0008_notifications
Revises: 0007_hospitals
Create Date: 2026-09-19 00:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_notifications"
down_revision: str | None = "0007_hospitals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTIFICATION_KIND_ENUM = postgresql.ENUM(
    "INCIDENT_STATUS_CHANGED",
    "INCIDENT_RECEIVED",
    "DISPATCH_ASSIGNED",
    "DISPATCH_CANCELLED",
    "HOSPITAL_NOTICE",
    "SYSTEM",
    name="notification_kind",
    create_type=False,
)
NOTIFICATION_CHANNEL_ENUM = postgresql.ENUM(
    "IN_APP",
    "SMS",
    "EMAIL",
    "PUSH",
    name="notification_channel",
    create_type=False,
)
DELIVERY_STATUS_ENUM = postgresql.ENUM(
    "PENDING",
    "DELIVERED",
    "FAILED",
    "UNAVAILABLE",
    name="delivery_status",
    create_type=False,
)

_NEW_ENUM_TYPES = (
    NOTIFICATION_KIND_ENUM,
    NOTIFICATION_CHANNEL_ENUM,
    DELIVERY_STATUS_ENUM,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _NEW_ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", NOTIFICATION_KIND_ENUM, nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=True),
        sa.Column("dispatch_id", sa.UUID(), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_notifications_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dispatch_id"],
            ["dispatches.id"],
            name=op.f("fk_notifications_dispatch_id_dispatches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"])
    op.create_index(op.f("ix_notifications_kind"), "notifications", ["kind"])
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read_at"])
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at"]
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("channel", NOTIFICATION_CHANNEL_ENUM, nullable=False),
        sa.Column("status", DELIVERY_STATUS_ENUM, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_notification_deliveries_notification_id_notifications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
    )
    op.create_index(
        op.f("ix_notification_deliveries_notification_id"),
        "notification_deliveries",
        ["notification_id"],
    )
    op.create_index(
        "ix_deliveries_channel_status",
        "notification_deliveries",
        ["channel", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_deliveries_channel_status", table_name="notification_deliveries")
    op.drop_index(
        op.f("ix_notification_deliveries_notification_id"),
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")

    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index(op.f("ix_notifications_kind"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")

    bind = op.get_bind()
    for enum_type in reversed(_NEW_ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)
