"""Column-level encryption for contact details (Phase 16).

Fernet — AES-128-CBC with an HMAC, so tampering is detected, not just hidden.
``docs/SECURITY.md`` section 10 records what this does and does not protect:
it keeps phone numbers unreadable in a database dump, a backup or a replica;
it does not protect against an attacker who holds the running application and
its key.

Only fields that are written once and displayed are encrypted. ``User.phone``
is not: it is unique and looked up, and ciphertext with a random IV can be
neither.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import Settings, get_settings


class DecryptionError(RuntimeError):
    """A stored value could not be decrypted with any configured key.

    Raised rather than swallowed: returning ciphertext where a phone number
    belongs would show a responder garbage during an emergency, silently.
    """


def _derived_key(secret: str) -> str:
    """A development/test key, domain-separated from the JWT signing use."""
    digest = hashlib.sha256(b"raksha-contact-encryption-v1:" + secret.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


@lru_cache
def _fernet(keys: tuple[str, ...]) -> MultiFernet:
    return MultiFernet([Fernet(key) for key in keys])


def _active(settings: Settings | None = None) -> MultiFernet:
    settings = settings or get_settings()
    if settings.encryption_key is not None:
        raw = settings.encryption_key.get_secret_value()
        keys = tuple(part.strip() for part in raw.split(",") if part.strip())
    else:
        keys = (_derived_key(settings.secret_key.get_secret_value()),)
    return _fernet(keys)


def encrypt_value(value: str | None, settings: Settings | None = None) -> str | None:
    if value is None:
        return None
    return _active(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_value(value: str | None, settings: Settings | None = None) -> str | None:
    if value is None:
        return None
    try:
        return _active(settings).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError) as exc:
        raise DecryptionError(
            "A stored contact detail could not be decrypted. "
            "Check RAKSHA_ENCRYPTION_KEY."
        ) from exc


def looks_encrypted(value: str) -> bool:
    """Whether ``value`` is already a Fernet token (used to make migrations re-runnable)."""
    return value.startswith("gAAAA")
