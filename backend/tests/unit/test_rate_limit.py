"""The rate limiter, without any service behind it."""

from __future__ import annotations

import subprocess
import sys

from app.core import metrics
from app.core.rate_limit import RateLimiter, build_rate_limiter, stable_key


def errors() -> float:
    return (
        metrics.REGISTRY.get_sample_value("raksha_rate_limit_backend_errors_total") or 0.0
    )


def test_requests_up_to_the_limit_are_allowed_then_refused() -> None:
    limiter = RateLimiter()
    decisions = [limiter.check("k", limit=3) for _ in range(5)]
    assert [d.allowed for d in decisions] == [True, True, True, False, False]
    assert [d.remaining for d in decisions[:3]] == [2, 1, 0]


def test_a_refusal_says_when_to_come_back() -> None:
    limiter = RateLimiter()
    limiter.check("k", limit=1)
    refused = limiter.check("k", limit=1, window_seconds=60)
    assert not refused.allowed
    assert 1 <= refused.retry_after <= 60


def test_keys_are_counted_independently() -> None:
    limiter = RateLimiter()
    assert limiter.check("a", limit=1).allowed
    assert not limiter.check("a", limit=1).allowed
    assert limiter.check("b", limit=1).allowed


def test_the_window_rolls_over(monkeypatch) -> None:
    import app.core.rate_limit as module

    clock = [1_000_000.0]
    monkeypatch.setattr(module.time, "time", lambda: clock[0])
    limiter = RateLimiter()
    assert limiter.check("k", limit=1).allowed
    assert not limiter.check("k", limit=1).allowed
    clock[0] += 61
    assert limiter.check("k", limit=1).allowed


def test_the_key_is_the_same_in_every_process() -> None:
    """Python's hash() is randomised per process; two API processes sharing a
    Redis must still agree on which counter a client belongs to."""
    code = (
        "from app.core.rate_limit import stable_key; print(stable_key('Bearer abc.def'))"
    )
    outputs = {
        subprocess.run(  # noqa: S603 - sys.executable running a fixed snippet
            [sys.executable, "-c", code],
            env={"PYTHONHASHSEED": seed, "PATH": "", "PYTHONPATH": "."},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for seed in ("1", "2", "3")
    }
    assert len(outputs) == 1
    assert outputs == {stable_key("Bearer abc.def")}


def test_the_key_does_not_contain_the_token() -> None:
    assert "secret-token" not in stable_key("Bearer secret-token")


# --- a failing shared store --------------------------------------------------
class DeadRedis:
    """Every command fails, and we count how often it was asked."""

    def __init__(self) -> None:
        self.calls = 0

    def pipeline(self):
        self.calls += 1
        raise ConnectionError("redis is down")


def test_a_failing_store_falls_back_to_counting_locally_not_to_allowing_all() -> None:
    limiter = RateLimiter(DeadRedis())
    assert [limiter.check("k", limit=2).allowed for _ in range(4)] == [
        True,
        True,
        False,
        False,
    ]


def test_a_failing_store_is_not_retried_on_every_request() -> None:
    dead = DeadRedis()
    limiter = RateLimiter(dead, retry_backend_after=60)
    for _ in range(10):
        limiter.check("k", limit=100)
    assert dead.calls == 1


def test_the_store_is_tried_again_after_the_wait(monkeypatch) -> None:
    import app.core.rate_limit as module

    dead = DeadRedis()
    limiter = RateLimiter(dead, retry_backend_after=5)
    now = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    limiter.check("k", limit=100)
    limiter.check("k", limit=100)
    assert dead.calls == 1
    now[0] += 6
    limiter.check("k", limit=100)
    assert dead.calls == 2


def test_each_failure_is_counted_so_the_degradation_is_visible() -> None:
    before = errors()
    limiter = RateLimiter(DeadRedis(), retry_backend_after=0)
    for _ in range(3):
        limiter.check("k", limit=100)
    assert errors() == before + 3


def test_the_memory_backend_is_the_default() -> None:
    from app.core.config import Settings

    limiter = build_rate_limiter(Settings())
    assert limiter._redis is None
