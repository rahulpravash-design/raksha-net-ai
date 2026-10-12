"""add TOTP MFA columns to users

Revision ID: 0011_mfa
Revises: 0010_encrypt_contact_details
Create Date: 2026-10-10 01:00:00.000000

``mfa_secret`` is encrypted at rest by the application (``EncryptedString``),
so it is widened to hold a Fernet token.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_mfa"
down_revision: str | None = "0010_encrypt_contact_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_last_step")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
