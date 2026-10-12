"""encrypt contact_phone at rest on incidents, resources and hospitals

Revision ID: 0010_encrypt_contact_details
Revises: 0009_account_lockout
Create Date: 2026-10-10 00:30:00.000000

The column widens first (a Fernet token is roughly four times the length of the
number it wraps), then every existing value is encrypted in place. The
downgrade decrypts and narrows again. Both directions skip a value already in
the target form, so a half-applied run can simply be run again.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.core.crypto import decrypt_value, encrypt_value, looks_encrypted

revision: str = "0010_encrypt_contact_details"
down_revision: str | None = "0009_account_lockout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("incidents", "resources", "hospitals")

_SELECT = {
    "incidents": "SELECT id, contact_phone FROM incidents WHERE contact_phone IS NOT NULL",
    "resources": "SELECT id, contact_phone FROM resources WHERE contact_phone IS NOT NULL",
    "hospitals": "SELECT id, contact_phone FROM hospitals WHERE contact_phone IS NOT NULL",
}
_UPDATE = {
    "incidents": "UPDATE incidents SET contact_phone = :v WHERE id = :id",
    "resources": "UPDATE resources SET contact_phone = :v WHERE id = :id",
    "hospitals": "UPDATE hospitals SET contact_phone = :v WHERE id = :id",
}


def _rewrite(table: str, transform: Callable[[str], str]) -> None:
    bind = op.get_bind()
    for row_id, value in bind.execute(sa.text(_SELECT[table])).all():
        new_value = transform(value)
        if new_value != value:
            bind.execute(sa.text(_UPDATE[table]), {"v": new_value, "id": row_id})


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(
            table,
            "contact_phone",
            existing_type=sa.String(length=32),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
        _rewrite(table, lambda v: v if looks_encrypted(v) else encrypt_value(v) or v)


def downgrade() -> None:
    for table in _TABLES:
        _rewrite(table, lambda v: (decrypt_value(v) or v) if looks_encrypted(v) else v)
        op.alter_column(
            table,
            "contact_phone",
            existing_type=sa.String(length=255),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
