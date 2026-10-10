"""Structured logging with per-request correlation IDs.

Sensitive keys are stripped from every log record. See ``docs/SECURITY.md``
section 9 — coordinates are treated as sensitive and are never logged.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "hashed_password",
        "token",
        "access_token",
        "refresh_token",
        "token_hash",
        "authorization",
        "secret",
        "secret_key",
        "api_key",
        "ai_api_key",
        "latitude",
        "longitude",
        "contact_phone",
        "mfa_code",
        "mfa_secret",
        "provisioning_uri",
        "encryption_key",
    }
)

REDACTED = "[redacted]"

_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def redact(payload: Any) -> Any:
    """Recursively replace sensitive values with a redaction marker."""
    if isinstance(payload, dict):
        return {
            key: (REDACTED if str(key).lower() in SENSITIVE_KEYS else redact(value))
            for key, value in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [redact(item) for item in payload]
    return payload


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id:
            entry["request_id"] = request_id

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRS and not key.startswith("_")
        }
        if extras:
            entry.update(redact(extras))

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable output for local development."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = request_id_var.get()
        prefix = f"[{request_id[:8]}] " if request_id else ""
        base = (
            f"{datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec='seconds')} "
            f"{record.levelname:<8} {prefix}{record.name}: {record.getMessage()}"
        )
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Install the root handler. Safe to call more than once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else ConsoleFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn installs its own handlers; route them through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
