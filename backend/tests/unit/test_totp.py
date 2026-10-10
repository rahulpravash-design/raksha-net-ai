"""RFC 6238 verification, including the replay rule."""

from __future__ import annotations

import pyotp

from app.core import totp

SECRET = pyotp.random_base32()
NOW = 1_800_000_000.0  # fixed, so no test depends on the wall clock
STEP = int(NOW // totp.STEP_SECONDS)


def code_at(offset_steps: int) -> str:
    return pyotp.TOTP(SECRET).at((STEP + offset_steps) * totp.STEP_SECONDS)


def test_the_current_code_is_accepted() -> None:
    assert totp.verify(SECRET, code_at(0), now=NOW) == STEP


def test_one_step_of_clock_drift_either_way_is_tolerated() -> None:
    assert totp.verify(SECRET, code_at(-1), now=NOW) == STEP - 1
    assert totp.verify(SECRET, code_at(1), now=NOW) == STEP + 1


def test_two_steps_away_is_refused() -> None:
    assert totp.verify(SECRET, code_at(-2), now=NOW) is None
    assert totp.verify(SECRET, code_at(2), now=NOW) is None


def test_a_wrong_code_is_refused() -> None:
    wrong = "000000" if code_at(0) != "000000" else "111111"
    assert totp.verify(SECRET, wrong, now=NOW) is None


def test_a_code_cannot_be_replayed() -> None:
    """Still inside the window, but already used — so no longer good."""
    assert totp.verify(SECRET, code_at(0), last_step=STEP, now=NOW) is None
    assert totp.verify(SECRET, code_at(-1), last_step=STEP, now=NOW) is None


def test_a_later_code_is_accepted_after_an_earlier_one() -> None:
    assert totp.verify(SECRET, code_at(1), last_step=STEP, now=NOW) == STEP + 1


def test_the_provisioning_uri_names_the_issuer_and_account() -> None:
    uri = totp.provisioning_uri(SECRET, "asha@example.org", "RAKSHA NET AI")
    assert uri.startswith("otpauth://totp/")
    assert "asha%40example.org" in uri
    assert "issuer=RAKSHA%20NET%20AI" in uri
