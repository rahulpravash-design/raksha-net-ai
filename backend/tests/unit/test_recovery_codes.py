"""Recovery code format, normalisation and hashing."""

from __future__ import annotations

import re

from app.core import recovery_codes
from app.core.config import get_settings


def test_codes_are_twelve_letters_in_three_groups() -> None:
    for code in recovery_codes.generate_codes():
        assert re.fullmatch(r"[A-Z]{4}-[A-Z]{4}-[A-Z]{4}", code)
        assert not set(code) & set("ILO")


def test_a_set_has_ten_distinct_codes_and_sets_differ() -> None:
    first, second = recovery_codes.generate_codes(), recovery_codes.generate_codes()
    assert len(first) == len(set(first)) == recovery_codes.CODES_PER_SET
    assert not set(first) & set(second)


def test_a_recovery_code_cannot_be_mistaken_for_an_authenticator_code() -> None:
    assert recovery_codes.is_totp_shaped("123456")
    assert not recovery_codes.is_totp_shaped("1234567")
    for code in recovery_codes.generate_codes():
        assert not recovery_codes.is_totp_shaped(code)
        assert not recovery_codes.is_totp_shaped(recovery_codes.normalise(code))


def test_typing_variations_hash_the_same() -> None:
    code = "ABCD-EFGH-JKMN"
    expected = recovery_codes.hash_code(code)
    for variant in (
        "abcd-efgh-jkmn",
        "ABCDEFGHJKMN",
        " abcd efgh jkmn ",
        "ABCD EFGH-JKMN",
    ):
        assert recovery_codes.hash_code(variant) == expected, variant
    assert recovery_codes.looks_like_recovery_code(" abcd efgh jkmn ")


def test_other_inputs_are_not_recovery_codes() -> None:
    for text in ("", "123456", "ABCD", "ABCD-EFGH-JKMN-PQRS", "hello"):
        assert not recovery_codes.looks_like_recovery_code(text), text


def test_the_hash_is_keyed_and_never_the_code() -> None:
    from pydantic import SecretStr

    code = "ABCD-EFGH-JKMN"
    base = get_settings()
    other = base.model_copy(
        update={"secret_key": SecretStr("another-secret-key-of-sufficient-length-1234")}
    )
    hashed = recovery_codes.hash_code(code, base)
    assert re.fullmatch(r"[0-9a-f]{64}", hashed)
    assert "ABCD" not in hashed
    # Without the server's key a stolen table cannot be used to test guesses.
    assert recovery_codes.hash_code(code, other) != hashed
