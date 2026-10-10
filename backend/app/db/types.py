"""Custom column types."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.crypto import decrypt_value, encrypt_value


class EncryptedString(TypeDecorator[str]):
    """A string stored as Fernet ciphertext, plaintext everywhere above the ORM.

    Services and repositories read and write ordinary strings; only what
    reaches PostgreSQL — and so any dump, backup or replica — is ciphertext.
    Raw SQL bypasses this type, so a query that selects an encrypted column by
    hand must call ``decrypt_value`` itself.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return encrypt_value(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        return decrypt_value(value)
