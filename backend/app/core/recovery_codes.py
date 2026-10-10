"""One-time recovery codes for accounts with two-factor authentication.

A user who loses their authenticator device would otherwise need an
administrator to reset their second factor — and an administrator cannot reset
their own, so a lone administrator who loses a phone would be locked out for good.
Recovery codes are the standard answer: a short list, shown once at enrolment,
each usable a single time in place of the six-digit code.

Design points:

* **Format.** Twelve letters from a 23-letter alphabet (no I, L or O), shown as
  ``ABCD-EFGH-JKMN`` — about 54 bits. Letters only, so a recovery code can never
  be mistaken for a six-digit TOTP code and the two are told apart by shape.
* **At rest.** Only a keyed hash is stored (HMAC-SHA256, key derived from the
  server secret with its own domain separator). The codes carry enough entropy
  that the hash is not offline-guessable, and the key means a stolen database
  alone cannot be used to test guesses at all.
* **Comparison.** Lookup is by the hash itself; the database never compares the
  plain code.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from app.core.config import Settings, get_settings

#: 23 letters: the alphabet minus I, L and O, which are easily misread.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 12
GROUP = 4
CODES_PER_SET = 10

_TOTP_SHAPE = re.compile(r"^\d{6}$")
_NON_LETTERS = re.compile(r"[^A-Z]")


def generate_code() -> str:
    letters = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return "-".join(letters[i : i + GROUP] for i in range(0, CODE_LENGTH, GROUP))


def generate_codes(count: int = CODES_PER_SET) -> list[str]:
    """``count`` distinct codes."""
    codes: set[str] = set()
    while len(codes) < count:
        codes.add(generate_code())
    return sorted(codes)


def is_totp_shaped(code: str) -> bool:
    """True for the six-digit form an authenticator app produces."""
    return bool(_TOTP_SHAPE.match(code))


def normalise(code: str) -> str:
    """Upper-case, drop spaces and dashes — how people type and copy these."""
    return _NON_LETTERS.sub("", code.upper())


def looks_like_recovery_code(code: str) -> bool:
    return len(normalise(code)) == CODE_LENGTH


def hash_code(code: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    key = hashlib.sha256(
        b"raksha-mfa-recovery-v1:" + settings.secret_key.get_secret_value().encode()
    ).digest()
    return hmac.new(key, normalise(code).encode("ascii"), hashlib.sha256).hexdigest()
