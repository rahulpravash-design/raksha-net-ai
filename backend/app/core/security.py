"""Password hashing and JSON Web Token handling.

``docs/SECURITY.md`` section 2 describes the policy this module implements.
Refresh tokens are deliberately *not* JWTs: they are opaque random values,
stored only as a SHA-256 hash so that a database disclosure does not yield
usable credentials.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import Settings, get_settings
from app.core.errors import InvalidTokenError, WeakPasswordError

TokenType = Literal["access"]

# bcrypt truncates at 72 bytes; rejecting longer input is clearer than
# silently ignoring the tail of a passphrase.
BCRYPT_MAX_BYTES = 72

_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password123",
        "123456789012",
        "qwertyuiopas",
        "administrator",
        "letmeinplease",
        "raksha123456",
    }
)


@dataclass(frozen=True, slots=True)
class AccessTokenPayload:
    """Decoded, validated access-token claims."""

    subject: uuid.UUID
    role: str
    jti: str
    expires_at: datetime


# -----------------------------------------------------------------------------
# Passwords
# -----------------------------------------------------------------------------
def validate_password_strength(password: str, settings: Settings | None = None) -> None:
    """Raise :class:`WeakPasswordError` if the password is unacceptable.

    Length is favoured over composition rules: a long passphrase beats a short
    string with a punctuation mark bolted on.
    """
    settings = settings or get_settings()
    problems: list[str] = []

    if len(password) < settings.password_min_length:
        problems.append(
            f"must be at least {settings.password_min_length} characters long"
        )
    if len(password) > settings.password_max_length:
        problems.append(f"must be at most {settings.password_max_length} characters")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        problems.append(f"must be at most {BCRYPT_MAX_BYTES} bytes when encoded")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("is too common")
    if password and len(set(password)) < 5:
        problems.append("must not repeat only a few characters")

    if problems:
        raise WeakPasswordError(
            message="Password " + "; ".join(problems) + ".",
            details={"problems": problems},
        )


def hash_password(password: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time-ish verification that never raises on malformed input."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# A pre-computed hash used to equalise the work done on an unknown-email login,
# so response timing does not reveal whether an account exists.
_DUMMY_HASH = bcrypt.hashpw(b"raksha-timing-equaliser", bcrypt.gensalt(rounds=12))


def burn_password_cycle() -> None:
    """Spend roughly one verification's worth of work on a non-existent user."""
    bcrypt.checkpw(b"raksha-timing-equaliser", _DUMMY_HASH)


# -----------------------------------------------------------------------------
# Access tokens (JWT)
# -----------------------------------------------------------------------------
def create_access_token(
    subject: uuid.UUID,
    role: str,
    *,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)``."""
    settings = settings or get_settings()
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    expires_at = now + delta

    claims: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(
        claims,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, int(delta.total_seconds())


def decode_access_token(
    token: str, settings: Settings | None = None
) -> AccessTokenPayload:
    """Decode and validate an access token, or raise :class:`InvalidTokenError`."""
    settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("The session has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError() from exc

    if claims.get("type") != "access":
        # A refresh token must never be usable as a bearer credential.
        raise InvalidTokenError()

    try:
        subject = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError() from exc

    role = claims.get("role")
    if not isinstance(role, str):
        raise InvalidTokenError()

    return AccessTokenPayload(
        subject=subject,
        role=role,
        jti=str(claims.get("jti", "")),
        expires_at=datetime.fromtimestamp(float(claims["exp"]), tz=UTC),
    )


# -----------------------------------------------------------------------------
# Refresh tokens (opaque)
# -----------------------------------------------------------------------------
def generate_refresh_token() -> tuple[str, str]:
    """Return ``(raw_token, sha256_hash)``. Only the hash is ever persisted."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
