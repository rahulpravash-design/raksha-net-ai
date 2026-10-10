"""Fixed-window rate limiting.

Two backends. ``memory`` keeps counters in the process: right for development,
tests and a single-process deployment, and *wrong* behind several processes,
where each keeps its own count and the effective limit is the configured one
times the number of processes. ``redis`` shares the counters, so the limit holds
however many processes there are (``RAKSHA_RATE_LIMIT_BACKEND``).

If Redis is configured but fails, requests are still counted locally rather than
allowed unchecked: a per-process limit is weaker than a shared one but far better
than none, and an outage of a supporting service should not remove a security
control. After a failure Redis is not tried again for a few seconds, so a dead
server costs one timeout, not one per request. Every failure increments
``raksha_rate_limit_backend_errors_total``, so the degradation is visible.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from app.core import metrics
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Seconds to leave a failed Redis alone before trying it again.
BACKEND_RETRY_SECONDS = 5.0
#: A dead Redis must cost milliseconds, not the driver's default of blocking.
REDIS_TIMEOUT_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int


def stable_key(identity: str) -> str:
    """A short, process-independent digest of a client identity.

    Python's built-in ``hash()`` is randomised per process, so two API processes
    would key the same client differently and never share a counter. A digest also
    keeps a bearer token out of the key (and so out of Redis).
    """
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


class RateLimiter:
    """Counts requests per ``(key, window)`` and allows up to ``limit``."""

    def __init__(
        self,
        redis_client: object | None = None,
        *,
        retry_backend_after: float = BACKEND_RETRY_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._retry_after = retry_backend_after
        self._backend_down_until = 0.0
        self._local: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitDecision:
        now = time.time()
        window_start = int(now // window_seconds) * window_seconds
        reset_at = window_start + window_seconds
        retry_after = max(1, int(reset_at - now))
        bucket = f"rl:{key}:{window_start}"

        count = self._increment(bucket, window_seconds)
        if count > limit:
            return RateLimitDecision(False, 0, retry_after)
        return RateLimitDecision(True, max(0, limit - count), retry_after)

    def reset(self) -> None:
        """Clear local counters. Used by tests."""
        with self._lock:
            self._local.clear()

    # -- internals ---------------------------------------------------------
    def _increment(self, bucket: str, ttl: int) -> int:
        if self._redis is not None and time.monotonic() >= self._backend_down_until:
            try:
                pipe = self._redis.pipeline()  # type: ignore[attr-defined]
                pipe.incr(bucket)
                pipe.expire(bucket, ttl)
                return int(pipe.execute()[0])
            except Exception:
                metrics.RATE_LIMIT_BACKEND_ERRORS.inc()
                self._backend_down_until = time.monotonic() + self._retry_after
                logger.warning("rate_limit_backend_unavailable", exc_info=True)
        return self._increment_local(bucket, ttl)

    def _increment_local(self, bucket: str, ttl: int) -> int:
        with self._lock:
            self._evict_expired()
            count, expiry = self._local.get(bucket, (0, time.time() + ttl))
            count += 1
            self._local[bucket] = (count, expiry)
            return count

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [key for key, (_, expiry) in self._local.items() if expiry < now]
        for key in expired:
            del self._local[key]


def build_rate_limiter(settings: Settings) -> RateLimiter:
    """The limiter the configuration asks for. A Redis client connects lazily, so
    constructing one does not fail when the server is down."""
    if settings.rate_limit_backend == "redis":
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
        )
        return RateLimiter(client)
    return RateLimiter()


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = build_rate_limiter(get_settings())
    return _limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Install a limiter (a fresh one for a test, or a prepared Redis one)."""
    global _limiter
    _limiter = limiter
