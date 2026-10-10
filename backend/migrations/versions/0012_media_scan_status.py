"""record the malware-scan result on uploaded media

Revision ID: 0012_media_scan_status
Revises: 0011_mfa
Create Date: 2026-10-10 02:00:00.000000

Existing rows are marked UNSCANNED, which is the truth: none of them was ever
scanned, and the column must not imply otherwise.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_media_scan_status"
down_revision: str | None = "0011_mfa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCAN_STATUS_ENUM = postgresql.ENUM(
    "CLEAN", "UNSCANNED", "INFECTED", name="scan_status", create_type=False
)


def upgrade() -> None:
    SCAN_STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "incident_media",
        sa.Column(
            "scan_status",
            SCAN_STATUS_ENUM,
            nullable=False,
            server_default="UNSCANNED",
        ),
    )


def downgrade() -> None:
    op.drop_column("incident_media", "scan_status")
    SCAN_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
