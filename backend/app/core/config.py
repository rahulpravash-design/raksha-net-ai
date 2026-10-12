"""Application configuration.

This module is the **only** place that reads the environment. Everything else
imports :func:`get_settings`. See ``CLAUDE.md`` section 4, rule 8.
"""

from __future__ import annotations

import base64
import secrets
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PLACEHOLDER_SECRET = "generate_a_unique_64_byte_secret_before_running"
REPO_ROOT = Path(__file__).resolve().parents[3]

#: URL schemes that managed PostgreSQL hosts (Render, Heroku, Railway ...) hand out.
#: SQLAlchemy reads a bare ``postgresql://`` as the psycopg2 driver, which this
#: project does not install; it ships psycopg 3, whose scheme is ``postgresql+psycopg``.
_PLAIN_POSTGRES_SCHEMES = ("postgresql://", "postgres://")
_PSYCOPG_SCHEME = "postgresql+psycopg://"


def normalise_database_url(url: str) -> str:
    """Return ``url`` in the form SQLAlchemy needs to use the installed driver.

    A host-supplied ``postgres://`` or ``postgresql://`` URL is rewritten to
    ``postgresql+psycopg://``; everything after the scheme (credentials, host, path,
    query such as ``sslmode``) is kept byte for byte. A URL that already names a
    driver is returned unchanged, so an explicit choice is never overridden.
    """
    stripped = url.strip()
    lowered = stripped.lower()
    for scheme in _PLAIN_POSTGRES_SCHEMES:
        if lowered.startswith(scheme):
            return _PSYCOPG_SCHEME + stripped[len(scheme) :]
    return stripped


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Runtime configuration, sourced from environment variables.

    Variables are prefixed ``RAKSHA_`` except for the ``POSTGRES_*`` and
    ``NEXT_PUBLIC_*`` families, which are shared with Docker Compose and the
    front ends and are read by explicit alias.
    """

    model_config = SettingsConfigDict(
        env_prefix="RAKSHA_",
        env_file=(REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    project_name: str = "RAKSHA NET AI"
    version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_format: str = "json"

    # --- Database ----------------------------------------------------------
    postgres_user: str = Field(default="raksha", alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(
        default=SecretStr("raksha_dev_password"), alias="POSTGRES_PASSWORD"
    )
    postgres_db: str = Field(default="raksha_net_ai", alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    #: A connection URL carries the database password, so it is a ``SecretStr``: it
    #: stays out of ``repr``, ``model_dump`` and any log line that prints settings.
    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 20
    #: Seconds a request waits for a free connection before giving up with a
    #: 503. SQLAlchemy's default is 30, which turns overload into a half-minute
    #: hang that ends as a 500.
    db_pool_timeout: float = 5.0
    db_echo: bool = False

    # --- Redis -------------------------------------------------------------
    #: May embed a password (``redis://:password@host``), hence a ``SecretStr``.
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    # --- Security ----------------------------------------------------------
    secret_key: SecretStr = SecretStr(PLACEHOLDER_SECRET)
    #: Fernet key(s) for column-level encryption of contact details. Separate
    #: from ``secret_key`` on purpose: rotating the token-signing secret must
    #: never make stored phone numbers unreadable. Comma-separate several to
    #: rotate — the first encrypts, all decrypt. Unset in development and test,
    #: where a key is derived from ``secret_key`` instead; required elsewhere.
    encryption_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    password_min_length: int = 12
    password_max_length: int = 128
    bcrypt_rounds: int = 12
    # ``NoDecode`` keeps pydantic-settings from JSON-parsing these before our
    # own validator runs, so a plain comma-separated value works in ``.env``.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
        ]
    )

    #: How many requests the API works on at once (per process). Held below the
    #: database pool *and* the worker-thread pool on purpose: a request can hold
    #: a connection while it waits for a thread, so admitting more than either
    #: lets connection-holders and thread-waiters block each other until the
    #: pool times out. Excess requests queue briefly, then get a 503. 0 disables.
    max_concurrent_requests: int = 24
    max_concurrent_wait_seconds: float = 3.0

    #: ``memory`` counts per process (development, tests, one process); ``redis``
    #: shares counters through ``redis_url`` so the limit holds across processes.
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10
    rate_limit_report_per_minute: int = 12
    #: Each transcription is a paid call to a third party; a reporter who hits this
    #: can still type, so it is lower than the report limit.
    rate_limit_transcription_per_minute: int = 6
    #: Proxies in front of the application that append to ``X-Forwarded-For`` (see
    #: ``app.core.client_address``). 0 = use the connecting address.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    #: Consecutive failed logins before an account is time-locked. Counted
    #: per account, not per client — rate limiting above already throttles by
    #: IP; this stops a distributed guess against one account.
    account_lockout_threshold: int = 5
    account_lockout_minutes: int = 15

    #: Name shown in an authenticator app once TOTP MFA is enrolled.
    mfa_issuer: str = "RAKSHA NET AI"
    #: When true, every non-citizen account must have MFA enabled before it can
    #: use the API (it may still sign in, read ``/auth/me`` and enrol). Off by
    #: default so development and the seeded accounts keep working; a
    #: production-like environment refuses to start with it off.
    mfa_required_for_operational: bool = False

    # --- Email (password recovery) ------------------------------------------
    #: SMTP server to send mail through. Unset means no email channel exists:
    #: the platform runs fully without it, and the sign-in screens say that
    #: self-service recovery is unavailable instead of promising a message.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    #: ``starttls`` upgrades a plain connection (port 587), ``ssl`` connects
    #: encrypted from the start (port 465), ``none`` is for a local test mailbox
    #: only — production-like environments refuse it.
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = 10.0
    email_from: str = "RAKSHA NET AI <no-reply@localhost>"
    #: How long a recovery link stays valid.
    password_reset_token_minutes: int = 30
    #: Recovery requests honoured per account per hour. More are accepted (so
    #: the response never reveals the account exists) but send nothing: this
    #: stops the form being used to flood someone's inbox.
    password_reset_max_per_hour: int = 3
    #: Where the recovery link points. Fixed by configuration, never taken from
    #: the request: a link built from a client-supplied host is how a reset token
    #: gets sent to an attacker's site.
    citizen_app_url: str = "http://localhost:3000"
    control_center_url: str = "http://localhost:3001"
    responder_app_url: str = "http://localhost:3002"

    # --- Observability -----------------------------------------------------
    #: Bearer token a metrics scraper must present to read ``/metrics``. Unset
    #: means the endpoint does not exist (404), not that it is open: metrics
    #: reveal traffic shape and internal route names.
    metrics_token: SecretStr | None = None

    # --- Media -------------------------------------------------------------
    media_storage_backend: str = "local"
    media_storage_path: Path = Path("./storage/media")
    media_max_bytes: int = 10 * 1024 * 1024
    media_allowed_mime: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )
    #: ClamAV daemon to scan uploads with. Unset means uploads are stored as
    #: ``UNSCANNED`` (see ``app/services/scanners.py``), not treated as clean.
    clamav_host: str | None = None
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 10.0
    #: If true, an upload is refused when the scanner cannot be reached.
    #: Default false: a photograph is secondary to the report it belongs to,
    #: and an outage in an optional tool must not stop a report being
    #: completed — the upload is kept as ``UNSCANNED`` and the fault logged.
    clamav_required: bool = False

    # --- Geospatial --------------------------------------------------------
    geo_srid: int = 4326
    geo_max_search_radius_km: float = 50.0
    geo_bbox_min_lat: float = 6.0
    geo_bbox_max_lat: float = 37.5
    geo_bbox_min_lon: float = 68.0
    geo_bbox_max_lon: float = 97.5

    # --- AI (Phase 6+) -----------------------------------------------------
    ai_enabled: bool = False
    #: Photo analysis (Phase 8). ``anthropic`` plus an API key turns it on; unset, an
    #: analysis reads the report's text only. Photos are sent to the provider only when
    #: an operator requests an analysis (docs/AI_ARCHITECTURE.md section 11).
    ai_provider: Literal["anthropic"] | None = None
    ai_api_key: SecretStr | None = None
    #: Unset = the provider's default model (ai/vision/claude_observer.py).
    ai_model: str | None = None
    ai_timeout_seconds: int = 20
    #: Voice reports (Phase 9). ``openai`` plus an API key, with ``ai_enabled``, offers a
    #: reporter dictation; unset, the report form offers typing only. A recording is sent
    #: to the provider once and discarded: it is never stored, only the transcript is
    #: (docs/AI_ARCHITECTURE.md section 11).
    speech_provider: Literal["openai"] | None = None
    speech_api_key: SecretStr | None = None
    #: Unset = ``whisper-1``. The model must return segment detail (``verbose_json``):
    #: the confidence every transcript records is computed from it.
    speech_model: str | None = None
    #: An OpenAI-compatible transcription service instead of OpenAI's own.
    speech_base_url: str | None = None
    speech_timeout_seconds: int = Field(default=30, ge=1, le=120)
    #: Two minutes of browser-recorded speech is well under 4 MB; 25 MB is OpenAI's limit.
    speech_max_bytes: int = Field(default=8 * 1024 * 1024, ge=1, le=25 * 1024 * 1024)

    # --- Priority engine (Phase 7) ------------------------------------------
    #: Which registered configuration is active. Rolling back to an earlier
    #: configuration, or pinning to one, needs only this value, not a deploy.
    priority_weights_version: str | None = None
    #: Optional JSON file defining a *new* configuration to register at
    #: startup (see `app/services/priority/config_loader.py`). Absent by
    #: default: the engine runs on its shipped V1 configuration.
    priority_weights_path: Path | None = None

    # ----------------------------------------------------------------------
    # Validators
    # ----------------------------------------------------------------------
    @field_validator("cors_origins", "media_allowed_mime", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept both a JSON array and a comma-separated string."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper

    # ----------------------------------------------------------------------
    # Derived values
    # ----------------------------------------------------------------------
    # A plain property, not a pydantic computed field: a computed field is part of
    # ``repr`` and ``model_dump``, and this value contains the database password.
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return normalise_database_url(self.database_url.get_secret_value())
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_host.strip())

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    @property
    def is_production_like(self) -> bool:
        return self.environment in (Environment.STAGING, Environment.PRODUCTION)

    @property
    def docs_url(self) -> str | None:
        return "/docs" if self.debug else None

    # ----------------------------------------------------------------------
    # Startup safety
    # ----------------------------------------------------------------------
    def assert_safe_for_environment(self) -> None:
        """Refuse to run with a development-grade configuration in production.

        Called from the application lifespan. Raising here is deliberate: a
        misconfigured emergency platform must fail to start rather than run
        insecurely.
        """
        if not self.is_production_like:
            return

        problems: list[str] = []
        if self.debug:
            problems.append("RAKSHA_DEBUG must be false outside development")
        if self.secret_key.get_secret_value() == PLACEHOLDER_SECRET:
            problems.append("RAKSHA_SECRET_KEY is still the placeholder value")
        if len(self.secret_key.get_secret_value()) < 32:
            problems.append("RAKSHA_SECRET_KEY must be at least 32 characters")
        if not self.mfa_required_for_operational:
            problems.append("RAKSHA_MFA_REQUIRED_FOR_OPERATIONAL must be true")
        if self.encryption_key is None:
            problems.append("RAKSHA_ENCRYPTION_KEY must be set outside development")
        elif not _all_fernet_keys(self.encryption_key.get_secret_value()):
            # Caught here, not at the first encrypted write (which would be a 500).
            problems.append(
                "RAKSHA_ENCRYPTION_KEY must be one or more comma-separated Fernet keys "
                "(url-safe base64 of 32 bytes)"
            )
        if "*" in self.cors_origins:
            problems.append("RAKSHA_CORS_ORIGINS must not contain '*'")
        if not self.cors_origins:
            problems.append("RAKSHA_CORS_ORIGINS must list the allowed origins")
        if any(origin.startswith("http://") for origin in self.cors_origins):
            problems.append("RAKSHA_CORS_ORIGINS must use https outside development")

        if self.speech_base_url and not self.speech_base_url.startswith("https://"):
            # Citizens' recordings must not cross a network in clear.
            problems.append("RAKSHA_SPEECH_BASE_URL must be an https:// URL")

        if self.email_configured:
            if self.smtp_security == "none":
                problems.append("RAKSHA_SMTP_SECURITY must be starttls or ssl")
            for name, url in (
                ("RAKSHA_CITIZEN_APP_URL", self.citizen_app_url),
                ("RAKSHA_CONTROL_CENTER_URL", self.control_center_url),
                ("RAKSHA_RESPONDER_APP_URL", self.responder_app_url),
            ):
                if not url.startswith("https://"):
                    problems.append(f"{name} must be an https:// URL when email is on")

        if problems:
            raise RuntimeError(
                "Unsafe configuration for environment "
                f"'{self.environment}':\n  - " + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


def _all_fernet_keys(raw: str) -> bool:
    """Whether every comma-separated part decodes to the 32 bytes a Fernet key is.

    The same test ``cryptography.fernet.Fernet`` applies, without importing it here.
    """
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    if not keys:
        return False
    for key in keys:
        try:
            if len(base64.urlsafe_b64decode(key.encode("ascii"))) != 32:
                return False
        except (ValueError, UnicodeError):
            return False
    return True


def generate_secret_key() -> str:
    """Helper used by ``scripts/`` to mint a development secret."""
    return secrets.token_urlsafe(64)


def generate_encryption_key() -> str:
    """A fresh Fernet key (urlsafe base64 of 32 random bytes)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
