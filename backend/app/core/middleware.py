"""HTTP middleware: correlation IDs, access logging, security headers, throttling."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.logging import get_logger, request_id_var
from app.core.rate_limit import get_rate_limiter

logger = get_logger("app.access")

RequestHandler = Callable[[Request], Awaitable[Response]]

#: Paths excluded from throttling and access logging noise.
PROBE_PATHS = frozenset({"/api/v1/health", "/api/v1/health/ready"})


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id, honouring one supplied by an upstream proxy."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        incoming = request.headers.get("X-Request-ID")
        # Bound the accepted value: a header is client-controlled input.
        request_id = (
            incoming[:64] if incoming and incoming.isprintable() else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """One structured log line per request, with its duration."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        if request.url.path not in PROBE_PATHS:
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else None,
                },
            )
        response.headers["X-Response-Time-ms"] = str(duration_ms)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Conservative defaults for an API that also serves uploaded files."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(self), microphone=(), camera=()"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Coarse per-client throttle across the whole API.

    Endpoint-specific limits (authentication, reporting) are applied in the
    endpoints themselves; this is the backstop.
    """

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        if not self.settings.rate_limit_enabled or request.url.path in PROBE_PATHS:
            return await call_next(request)

        identity = request.headers.get("authorization") or (
            request.client.host if request.client else "unknown"
        )
        key = f"api:{hash(identity) & 0xFFFFFFFF}"
        decision = get_rate_limiter().check(
            key, self.settings.rate_limit_default_per_minute
        )

        if not decision.allowed:
            error = RateLimitedError(retry_after=decision.retry_after)
            return JSONResponse(
                status_code=error.status_code,
                content=error.to_payload(),
                headers={"Retry-After": str(decision.retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response
