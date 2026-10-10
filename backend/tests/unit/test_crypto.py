"""Column-level encryption of contact details."""

from __future__ import annotations

import pytest

from app.core.config import Settings, generate_encryption_key
from app.core.crypto import DecryptionError, decrypt_value, encrypt_value

SETTINGS = Settings(secret_key="unit-test-secret-key-0123456789abcdef")


def test_round_trip() -> None:
    token = encrypt_value("+919876543210", SETTINGS)
    assert token != "+919876543210"
    assert decrypt_value(token, SETTINGS) == "+919876543210"


def test_none_passes_through() -> None:
    assert encrypt_value(None, SETTINGS) is None
    assert decrypt_value(None, SETTINGS) is None


def test_encryption_is_randomised() -> None:
    """The same number must not produce the same ciphertext twice."""
    assert encrypt_value("+911234567890", SETTINGS) != encrypt_value(
        "+911234567890", SETTINGS
    )


def test_the_wrong_key_fails_loudly() -> None:
    token = encrypt_value("+919876543210", SETTINGS)
    other = Settings(secret_key="a-completely-different-secret-key-value-here")
    with pytest.raises(DecryptionError):
        decrypt_value(token, other)


def test_a_tampered_value_is_rejected() -> None:
    token = encrypt_value("+919876543210", SETTINGS)
    assert token is not None
    flipped = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    with pytest.raises(DecryptionError):
        decrypt_value(flipped, SETTINGS)


def test_rotating_the_signing_secret_does_not_orphan_the_data() -> None:
    """The point of a dedicated key: SECRET_KEY rotation must not destroy data."""
    key = generate_encryption_key()
    before = Settings(
        secret_key="first-secret-key-0123456789abcdef-aaaa", encryption_key=key
    )
    after = Settings(
        secret_key="second-secret-key-0123456789abcdef-bbb", encryption_key=key
    )
    token = encrypt_value("+919876543210", before)
    assert decrypt_value(token, after) == "+919876543210"


def test_key_rotation_decrypts_old_values_and_encrypts_with_the_new_key() -> None:
    old, new = generate_encryption_key(), generate_encryption_key()
    old_only = Settings(encryption_key=old)
    rotated = Settings(encryption_key=f"{new},{old}")
    new_only = Settings(encryption_key=new)

    legacy = encrypt_value("+919876543210", old_only)
    assert decrypt_value(legacy, rotated) == "+919876543210"
    fresh = encrypt_value("+919876543210", rotated)
    assert decrypt_value(fresh, new_only) == "+919876543210"


def test_production_refuses_to_start_without_an_encryption_key() -> None:
    settings = Settings(
        environment="production",
        debug=False,
        secret_key="a-production-grade-secret-key-0123456789",
        cors_origins=["https://app.example.org"],
    )
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        settings.assert_safe_for_environment()
