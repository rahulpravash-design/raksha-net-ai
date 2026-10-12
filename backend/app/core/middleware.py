"""HTTP middleware: correlation IDs, access logging, security headers, throttling."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core import metrics
from app.core.config import Settings
from app.core.errors import RateLimitedError, ServiceBusyError, unexpected_error_response
from app.core.logging import get_logger, request_id_var
from app.core.rate_limit import get_rate_limiter, stable_key

logger = get_logger("app.access")

RequestHandler = Callable[[Request], Awaitable[Response]]

#: Paths excluded from throttling and access logging noise.
#: ``/metrics`` is here so that, under overload, the monitoring that would show
#: the overload is not itself shed, throttled or logged.
PROBE_PATHS = frozenset({"/api/v1/health", "/api/v1/health/ready", "/metrics"})


class UnhandledErrorMiddleware(BaseHTTPMiddleware):
    """Turn an uncaught exception into the 500 envelope *inside* the other middleware.

    Starlette answers an uncaught exception from its outermost layer, outside CORS, so
    that response carried no ``Access-Control-Allow-Origin``. A browser then hides the
    status and shows a bare network failure, and a bug in the backend reads to the
    visitor as "could not reach the server". Registered first, so it is innermost: the
    response it returns passes back out through CORS, the request id and the access log
    like any other. Only failures before the response starts can be turned into a
    response; one during streaming still propagates.
    """

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:  # the boundary: nothing may escape unlogged
            return unexpected_error_response(exc)


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


#: The interactive API docs (dev-only — see ``Settings.docs_url``) load their
#: own script and style from a CDN, which the strict CSP below forbids. Every
#: other response on this API is JSON and needs no script, style or frame
#: allowance at all.
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})

#: An API that returns JSON has no legitimate use for a script, a style sheet,
#: a frame or a plugin. ``default-src 'none'`` denies everything and nothing
#: is re-permitted, so this also satisfies ``docs/SECURITY.md`` section 6's
#: requirement to forbid inline script.
_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Conservative defaults for an API that also serves uploaded files."""

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(self), microphone=(), camera=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.url.path not in _DOCS_PATHS:
            response.headers.setdefault("Content-Security-Policy", _CSP)
        if self.settings.is_production_like:
            # Meaningful only over HTTPS — browsers ignore it on plain HTTP —
            # so it is harmless to send in a development/test response too,
            # but only asserted here where TLS is the deployment's own rule.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Count and time every request, labelled by route template.

    Registered outside :class:`ConcurrencyLimitMiddleware`, so a request that is
    queued or shed is still counted and its wait is part of its latency.
    """

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._prefix = settings.api_v1_prefix.rstrip("/")

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        if request.url.path in PROBE_PATHS:
            return await call_next(request)

        started = time.perf_counter()
        metrics.HTTP_IN_FLIGHT.inc()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            metrics.HTTP_IN_FLIGHT.dec()
            # The router stores the matched route on the scope as it dispatches,
            # so it is only readable once the request has been handled.
            label = self._route_label(request)
            metrics.HTTP_REQUESTS.labels(request.method, label, str(status_code)).inc()
            metrics.HTTP_LATENCY.labels(label).observe(time.perf_counter() - started)

    def _route_label(self, request: Request) -> str:
        # An included router reports its path *without* the mount prefix
        # (``/incidents/{incident_id}``, not ``/api/v1/incidents/...``), and the
        # prefix is not on the scope, so it is put back for requests that arrived
        # under it. A request that matched nothing gets one shared label.
        path = getattr(request.scope.get("route"), "path", None)
        if path is None:
            return metrics.UNMATCHED_ROUTE
        if self._prefix and request.url.path.startswith(f"{self._prefix}/"):
            return f"{self._prefix}{path}"
        return str(path)


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    """Admit only as many requests as the API can actually serve at once.

    Without this, overload deadlocks rather than slowing down: a request holds a
    database connection while it waits for a worker thread, and the worker
    threads are all blocked waiting for connections. Measured, not assumed — see
    ``docs/PERFORMANCE.md``. A request over the limit waits briefly (a surge
    clears in moments) and is then refused with ``503`` and ``Retry-After``,
    which a client can act on, instead of hanging for the pool timeout.
    """

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        limit = settings.max_concurrent_requests
        self._wait = settings.max_concurrent_wait_seconds
        self._semaphore = asyncio.Semaphore(limit) if limit > 0 else None

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        if self._semaphore is None or request.url.path in PROBE_PATHS:
            return await call_next(request)
        if self._semaphore.locked():
            metrics.REQUESTS_QUEUED.inc()
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=self._wait)
            except TimeoutError:
                metrics.REQUESTS_SHED.inc()
                error = ServiceBusyError(retry_after=1)
                return JSONResponse(
                    status_code=error.status_code,
                    content=error.to_payload(),
                    headers={"Retry-After": str(error.retry_after)},
                )
        else:
            # A slot is free, so this takes it without suspending. That matters:
            # going through ``wait_for`` would defer the acquire to a new task,
            # and requests arriving together would all see "not full" and none
            # would be counted as queued.
            await self._semaphore.acquire()
        try:
            return await call_next(request)
        finally:
            self._semaphore.release()


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
        key = f"api:{stable_key(identity)}"
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
