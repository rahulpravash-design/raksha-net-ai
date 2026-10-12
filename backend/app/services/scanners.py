"""The boundary between the upload path and a malware scanner (Phase 16).

Same shape as the AI and notification boundaries, for the same reason: the
platform must keep accepting reports with the scanner absent. With no scanner
configured, :class:`NullScanner` marks an upload ``UNSCANNED`` — a visible
fact on the record, never a silent "clean". With ClamAV configured,
:class:`ClamdScanner` speaks clamd's ``INSTREAM`` protocol over TCP.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.config import Settings
from app.models.enums import ScanStatus

_CHUNK = 64 * 1024


class ScannerUnavailableError(RuntimeError):
    """The scanner is configured but could not give an answer."""


@dataclass(frozen=True, slots=True)
class ScanOutcome:
    status: ScanStatus
    #: For ``INFECTED``, the signature name the scanner reported.
    detail: str | None = None


@runtime_checkable
class Scanner(Protocol):
    def scan(self, content: bytes) -> ScanOutcome: ...


class NullScanner:
    """Declines to scan, and the record says so."""

    def scan(self, content: bytes) -> ScanOutcome:
        return ScanOutcome(
            status=ScanStatus.UNSCANNED,
            detail="No malware scanner is configured for this deployment.",
        )


class ClamdScanner:
    """A ClamAV daemon client (``clamd``'s ``zINSTREAM`` command)."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def scan(self, content: bytes) -> ScanOutcome:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            ) as conn:
                conn.sendall(b"zINSTREAM\0")
                for start in range(0, len(content), _CHUNK):
                    chunk = content[start : start + _CHUNK]
                    conn.sendall(struct.pack(">I", len(chunk)) + chunk)
                conn.sendall(struct.pack(">I", 0))
                reply = self._read_reply(conn)
        except OSError as exc:
            raise ScannerUnavailableError(
                f"Could not reach the malware scanner: {exc}"
            ) from exc
        return self._interpret(reply)

    @staticmethod
    def _read_reply(conn: socket.socket) -> str:
        data = b""
        while not data.endswith(b"\0"):
            piece = conn.recv(4096)
            if not piece:
                break
            data += piece
        return data.rstrip(b"\0").decode("utf-8", errors="replace").strip()

    @staticmethod
    def _interpret(reply: str) -> ScanOutcome:
        # "stream: OK" | "stream: <signature> FOUND" | "<message> ERROR"
        if reply.endswith("FOUND"):
            signature = reply.removeprefix("stream:").removesuffix("FOUND").strip()
            return ScanOutcome(ScanStatus.INFECTED, signature or "unknown")
        if reply.endswith("OK"):
            return ScanOutcome(ScanStatus.CLEAN)
        raise ScannerUnavailableError(f"Unexpected scanner reply: {reply or '(empty)'}")


def get_scanner(settings: Settings) -> Scanner:
    if settings.clamav_host:
        return ClamdScanner(
            settings.clamav_host,
            settings.clamav_port,
            settings.clamav_timeout_seconds,
        )
    return NullScanner()
