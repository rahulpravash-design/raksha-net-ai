"""Fixed-window rate limiting.

Redis-backed when a client is available, with an in-process fallback so that
local development and the test suite need no extra service. The fallback is
explicitly *not* suitable for a multi-process deployment; the readiness of a
shared backend is a production checklist item.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter:
    """Counts requests per ``(key, window)`` and allows up to ``limit``."""

    def __init__(self, redis_client: object | None = None) -> None:
        self._redis = redis_client
        self._local: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitDecision:
        now = time.time()
        window_start = int(now // window_seconds) * window_seconds
        reset_at = window_start + window_seconds
        retry_after = max(1, int(reset_at - now))
        bucket = f"rl:{key}:{window_start}"

        count = self._increment(bucket, window_seconds)
        if count is None:  # backend failure — fail open, but say so
            return RateLimitDecision(True, limit, 0)

        if count > limit:
            return RateLimitDecision(False, 0, retry_after)
        return RateLimitDecision(True, max(0, limit - count), retry_after)

    def reset(self) -> None:
        """Clear local counters. Used by tests."""
        with self._lock:
            self._local.clear()

    # -- internals ---------------------------------------------------------
    def _increment(self, bucket: str, ttl: int) -> int | None:
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()  # type: ignore[attr-defined]
                pipe.incr(bucket)
                pipe.expire(bucket, ttl)
                return int(pipe.execute()[0])
            except Exception:
                logger.warning("rate_limit_backend_unavailable", exc_info=True)
                return None

        with self._lock:
            self._evict_expired()
            count, _ = self._local.get(bucket, (0, time.time() + ttl))
            count += 1
            self._local[bucket] = (count, time.time() + ttl)
            return count

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [key for key, (_, expiry) in self._local.items() if expiry < now]
        for key in expired:
            del self._local[key]


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Install a limiter (Redis-backed, or a fresh one for a test)."""
    global _limiter
    _limiter = limiter
