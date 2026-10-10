"""users.must_change_password

Revision ID: 0014_must_change_password
Revises: 0013_incident_created_at_index
Create Date: 2026-10-10 09:00:00.000000

An administrator-set password (creation or reset) is known to the administrator
and to whoever they passed it on to, so the account must replace it before it can
be used for anything else. Existing accounts are not affected (default false).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_must_change_password"
down_revision: str | None = "0013_incident_created_at_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
