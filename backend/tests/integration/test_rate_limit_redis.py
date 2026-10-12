"""The Redis-backed limiter, against a real ``redis-server`` process.

Skipped when the binary is not installed. A fake would only prove the fake: what
matters is that counters are really shared, really expire, and that an outage
degrades to local counting instead of failing requests.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time

import pytest
import redis

from app.core import metrics
from app.core.config import Settings
from app.core.rate_limit import RateLimiter, build_rate_limiter, stable_key

pytestmark = pytest.mark.skipif(
    shutil.which("redis-server") is None, reason="redis-server is not installed"
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class RedisProcess:
    def __init__(self) -> None:
        self.port = free_port()
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        executable = shutil.which("redis-server")
        assert executable is not None  # the module is skipped otherwise
        # A fixed, trusted binary with arguments built from an int we chose.
        self.proc = subprocess.Popen(  # noqa: S603
            [
                executable,
                "--port",
                str(self.port),
                "--bind",
                "127.0.0.1",
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                if self.client().ping():
                    return
            except redis.RedisError:
                time.sleep(0.05)
        raise RuntimeError("redis-server did not start")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait(timeout=5)
            self.proc = None

    def client(self) -> redis.Redis:
        return redis.Redis(
            host="127.0.0.1",
            port=self.port,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )


@pytest.fixture
def server():
    process = RedisProcess()
    process.start()
    yield process
    process.stop()


def errors() -> float:
    return (
        metrics.REGISTRY.get_sample_value("raksha_rate_limit_backend_errors_total") or 0.0
    )


def test_two_processes_share_one_limit(server: RedisProcess) -> None:
    """The reason this backend exists."""
    first = RateLimiter(server.client())
    second = RateLimiter(server.client())
    key = stable_key("203.0.113.9")

    allowed = [first.check(key, limit=6).allowed for _ in range(3)]
    allowed += [second.check(key, limit=6).allowed for _ in range(3)]
    assert allowed == [True] * 6
    assert not first.check(key, limit=6).allowed
    assert not second.check(key, limit=6).allowed


def test_without_redis_each_process_has_its_own_limit() -> None:
    """The multiplication that makes the memory backend wrong for several processes."""
    first, second = RateLimiter(), RateLimiter()
    total = sum(first.check("k", limit=6).allowed for _ in range(10))
    total += sum(second.check("k", limit=6).allowed for _ in range(10))
    assert total == 12  # twice the configured 6


def test_counters_expire(server: RedisProcess) -> None:
    limiter = RateLimiter(server.client())
    limiter.check("k", limit=5, window_seconds=60)
    keys = server.client().keys("rl:k:*")
    assert len(keys) == 1
    assert 0 < server.client().ttl(keys[0]) <= 60


def test_the_configured_backend_connects_through_the_url(server: RedisProcess) -> None:
    settings = Settings(
        rate_limit_backend="redis", redis_url=f"redis://127.0.0.1:{server.port}/0"
    )
    first, second = build_rate_limiter(settings), build_rate_limiter(settings)
    assert first.check("shared", limit=2).allowed
    assert second.check("shared", limit=2).allowed
    assert not first.check("shared", limit=2).allowed


def test_losing_redis_degrades_to_local_counting(server: RedisProcess) -> None:
    limiter = RateLimiter(server.client(), retry_backend_after=60)
    assert limiter.check("k", limit=3).allowed
    before = errors()

    server.stop()

    # No exception, and the limit still holds. It is counted locally from zero:
    # the one request already recorded in Redis is not known here, so up to
    # `limit` more are allowed during the outage. That is the price of falling
    # back, and why the error counter exists.
    decisions = [limiter.check("k", limit=3).allowed for _ in range(5)]
    assert decisions == [True, True, True, False, False]
    assert errors() == before + 1


def test_the_shared_store_is_used_again_once_it_recovers(server: RedisProcess) -> None:
    limiter = RateLimiter(server.client(), retry_backend_after=0.1)
    server.stop()
    limiter.check("k", limit=10)  # fails, falls back

    server.start()
    time.sleep(0.2)
    limiter.check("k", limit=10)
    assert len(server.client().keys("rl:k:*")) == 1
