"""RAKSHA NET AI — API application factory.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.metrics import router as metrics_router
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    AccessLogMiddleware,
    ConcurrencyLimitMiddleware,
    CorrelationIdMiddleware,
    MetricsMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
)

logger = get_logger(__name__)

DESCRIPTION = """
AI-assisted emergency response and resource coordination.

**AI is decision support, not autonomous emergency command.** Structured
information may be extracted automatically, but operational priority is
computed by a deterministic, auditable engine and every dispatch decision is
taken by an authorised human operator.
""".strip()


def _build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Refuse to serve with a development-grade configuration in production.
        settings.assert_safe_for_environment()

        if (
            settings.is_production_like
            and settings.rate_limit_enabled
            and settings.rate_limit_backend == "memory"
        ):
            logger.warning(
                "rate_limit_is_per_process",
                extra={
                    "detail": "RAKSHA_RATE_LIMIT_BACKEND=memory: with several API "
                    "processes the effective limit is multiplied by their number."
                },
            )

        if settings.media_storage_backend == "local":
            settings.media_storage_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "application_started",
            extra={
                "environment": settings.environment.value,
                "version": settings.version,
                "ai_enabled": settings.ai_enabled,
            },
        )
        yield
        logger.info("application_stopped")

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title=settings.project_name,
        description=DESCRIPTION,
        version=settings.version,
        docs_url=settings.docs_url,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=_build_lifespan(settings),
    )

    # Middleware runs in reverse registration order, so the correlation id is
    # registered last and therefore wraps everything else.
    # First registered = innermost: an uncaught exception becomes a response here, so it
    # still passes back out through CORS (see UnhandledErrorMiddleware).
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(ConcurrencyLimitMiddleware, settings=settings)
    app.add_middleware(MetricsMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    # Outside /api/v1 on purpose: it is operational, not part of the public API,
    # and a proxy that forwards only /api/ cannot expose it by accident.
    app.include_router(metrics_router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "name": settings.project_name,
            "version": settings.version,
            "health": f"{settings.api_v1_prefix}/health",
        }

    return app


app = create_app()
