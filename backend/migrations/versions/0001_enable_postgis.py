"""Enable the PostGIS extension.

Kept as its own revision because extension creation needs elevated privileges
and is often performed by a DBA ahead of the application migrations.

Revision ID: 0001_postgis
Revises:
Create Date: Phase 0
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_postgis"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # Deliberately not dropped: other schemas in the same database may depend on
    # it, and dropping an extension cascades into their data.
    pass
