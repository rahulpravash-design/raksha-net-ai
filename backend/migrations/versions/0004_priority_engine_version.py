"""record the priority engine configuration version on each incident

Revision ID: 0004_priority_version
Revises: 0003_incident_analyses
Create Date: 2026-09-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_priority_version"
down_revision: str | None = "0003_incident_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable rather than backfilled to a guess: rows scored before this
    # column existed genuinely do not record which configuration produced
    # them, and saying so honestly beats asserting "1.0.0" for scores nobody
    # verified were computed under it.
    op.add_column(
        "incidents",
        sa.Column("priority_engine_version", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "priority_engine_version")
