"""Password hashing and token handling."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.config import Settings
from app.core.errors import InvalidTokenError, WeakPasswordError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)

SETTINGS = Settings(bcrypt_rounds=4, secret_key="unit-test-secret-key-0123456789abcdef")
GOOD_PASSWORD = "a-long-enough-passphrase"


def test_hash_is_salted_and_verifiable() -> None:
    first = hash_password(GOOD_PASSWORD, SETTINGS)
    second = hash_password(GOOD_PASSWORD, SETTINGS)
    assert first != second  # distinct salts
    assert verify_password(GOOD_PASSWORD, first)
    assert verify_password(GOOD_PASSWORD, second)


def test_wrong_password_fails() -> None:
    assert not verify_password(
        "something else entirely", hash_password(GOOD_PASSWORD, SETTINGS)
    )


def test_verify_never_raises_on_a_malformed_hash() -> None:
    assert verify_password(GOOD_PASSWORD, "not-a-bcrypt-hash") is False
    assert verify_password(GOOD_PASSWORD, "") is False


@pytest.mark.parametrize(
    "password",
    ["short", "password123", "aaaaaaaaaaaaaaaa", "x" * 200],
)
def test_weak_passwords_are_rejected(password: str) -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength(password, SETTINGS)


def test_a_long_passphrase_is_accepted() -> None:
    validate_password_strength("river lantern copper window", SETTINGS)


def test_password_beyond_the_bcrypt_limit_is_rejected() -> None:
    """bcrypt truncates at 72 bytes; silently ignoring the tail would make two
    different passphrases interchangeable."""
    with pytest.raises(WeakPasswordError):
        validate_password_strength("é" * 40, SETTINGS)


def test_access_token_round_trip() -> None:
    subject = uuid.uuid4()
    token, expires_in = create_access_token(subject, "DISPATCHER", settings=SETTINGS)
    payload = decode_access_token(token, SETTINGS)
    assert payload.subject == subject
    assert payload.role == "DISPATCHER"
    assert expires_in == SETTINGS.access_token_expire_minutes * 60


def test_expired_token_is_rejected() -> None:
    token, _ = create_access_token(
        uuid.uuid4(), "CITIZEN", settings=SETTINGS, expires_delta=timedelta(seconds=-10)
    )
    with pytest.raises(InvalidTokenError) as excinfo:
        decode_access_token(token, SETTINGS)
    assert excinfo.value.code == "TOKEN_EXPIRED"


def test_token_signed_with_another_key_is_rejected() -> None:
    other = Settings(secret_key="a-completely-different-secret-key-value-here")
    token, _ = create_access_token(uuid.uuid4(), "CITIZEN", settings=other)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.token", SETTINGS)


def test_refresh_token_is_opaque_and_only_its_hash_is_reproducible() -> None:
    raw, digest = generate_refresh_token()
    assert len(raw) >= 43  # 48 random bytes, urlsafe-encoded
    assert digest == hash_refresh_token(raw)
    assert raw not in digest


def test_two_refresh_tokens_are_distinct() -> None:
    assert generate_refresh_token()[0] != generate_refresh_token()[0]
