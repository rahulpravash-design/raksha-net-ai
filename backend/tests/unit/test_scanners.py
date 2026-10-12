"""The clamd client, against a fake daemon that speaks the real wire format.

This verifies the protocol handling. It does not prove behaviour against an
actual ClamAV, which this environment does not have.
"""

from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from app.core.config import Settings
from app.models.enums import ScanStatus
from app.services.scanners import (
    ClamdScanner,
    NullScanner,
    ScannerUnavailableError,
    get_scanner,
)


@contextmanager
def fake_clamd(reply: bytes) -> Iterator[tuple[int, list[bytes]]]:
    """A one-shot clamd. Yields its port and the payload it received."""
    received: list[bytes] = []
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    def serve() -> None:
        conn, _ = server.accept()
        with conn:
            buffer = b""
            while not buffer.startswith(b"zINSTREAM\0"):
                buffer += conn.recv(4096)
            buffer = buffer[len(b"zINSTREAM\0") :]
            payload = b""
            while True:
                while len(buffer) < 4:
                    buffer += conn.recv(4096)
                (size,) = struct.unpack(">I", buffer[:4])
                buffer = buffer[4:]
                if size == 0:
                    break
                while len(buffer) < size:
                    buffer += conn.recv(4096)
                payload += buffer[:size]
                buffer = buffer[size:]
            received.append(payload)
            conn.sendall(reply)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1], received
    finally:
        server.close()
        thread.join(timeout=2)


def scanner(port: int) -> ClamdScanner:
    return ClamdScanner("127.0.0.1", port, timeout=2)


def test_a_clean_file_is_reported_clean() -> None:
    with fake_clamd(b"stream: OK\0") as (port, received):
        outcome = scanner(port).scan(b"harmless bytes")
    assert outcome.status is ScanStatus.CLEAN
    assert received == [b"harmless bytes"]


def test_an_infected_file_reports_the_signature() -> None:
    with fake_clamd(b"stream: Eicar-Test-Signature FOUND\0") as (port, _):
        outcome = scanner(port).scan(b"X5O!P%@AP")
    assert outcome.status is ScanStatus.INFECTED
    assert outcome.detail == "Eicar-Test-Signature"


def test_a_large_file_is_streamed_in_chunks_and_arrives_whole() -> None:
    content = bytes(range(256)) * 1024  # 256 KiB: several 64 KiB chunks
    with fake_clamd(b"stream: OK\0") as (port, received):
        scanner(port).scan(content)
    assert received == [content]


def test_an_error_reply_is_not_mistaken_for_clean() -> None:
    with (
        fake_clamd(b"INSTREAM size limit exceeded. ERROR\0") as (port, _),
        pytest.raises(ScannerUnavailableError),
    ):
        scanner(port).scan(b"data")


def test_an_empty_reply_is_not_mistaken_for_clean() -> None:
    with fake_clamd(b"") as (port, _), pytest.raises(ScannerUnavailableError):
        scanner(port).scan(b"data")


def test_an_unreachable_daemon_raises_rather_than_passing_the_file() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()  # nothing is listening here now
    with pytest.raises(ScannerUnavailableError):
        scanner(port).scan(b"data")


def test_with_nothing_configured_the_scanner_declines_honestly() -> None:
    outcome = get_scanner(Settings()).scan(b"data")
    assert outcome.status is ScanStatus.UNSCANNED
    assert "No malware scanner" in (outcome.detail or "")


def test_configuring_a_host_selects_the_clamd_client() -> None:
    assert isinstance(get_scanner(Settings(clamav_host="clamav")), ClamdScanner)
    assert isinstance(get_scanner(Settings()), NullScanner)
