"""RFC 6238 time-based one-time passwords for MFA (Phase 16).

A thin layer over ``pyotp`` that adds what ``pyotp.TOTP.verify`` does not do:
report *which* time step matched, so the caller can refuse a replay. A code
that was already accepted stays mathematically valid for up to a minute, which
is long enough for someone who watched it being typed to reuse it.
"""

from __future__ import annotations

import hmac
import time

import pyotp

STEP_SECONDS = 30
#: Accept the previous and next step too, to tolerate clock drift between the
#: server and a phone. One step either side is the RFC's recommended maximum.
DRIFT_STEPS = 1


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def verify(
    secret: str,
    code: str,
    *,
    last_step: int | None = None,
    now: float | None = None,
) -> int | None:
    """Return the matching time step, or ``None`` if the code is not acceptable.

    A step at or before ``last_step`` is refused as a replay.
    """
    totp = pyotp.TOTP(secret, interval=STEP_SECONDS)
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        expected = totp.at(step * STEP_SECONDS)
        if hmac.compare_digest(expected, code):
            if last_step is not None and step <= last_step:
                return None
            return step
    return None
