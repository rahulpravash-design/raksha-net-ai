"""Human-usable reference codes.

A citizen reads this code out over the phone, so the alphabet excludes
characters that are easily confused when spoken or written: I/1, O/0, S/5, Z/2.
"""

from __future__ import annotations

import secrets

REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRTUVWXY346789"
REFERENCE_PREFIX = "RKS"
REFERENCE_LENGTH = 6


def generate_reference_code() -> str:
    """Return a code such as ``RKS-8F3K2Q``."""
    body = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH))
    return f"{REFERENCE_PREFIX}-{body}"
