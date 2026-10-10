"""index incidents.created_at

Revision ID: 0013_incident_created_at_index
Revises: 0012_media_scan_status
Create Date: 2026-10-10 04:00:00.000000

Added on evidence, not by habit: at 100k incidents a deep page of the
newest-first history did a full scan and an on-disk sort (p95 481 ms); with this
index it reads in index order (p95 170 ms). See docs/PERFORMANCE.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_incident_created_at_index"
down_revision: str | None = "0012_media_scan_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_incidents_created_at", table_name="incidents")
