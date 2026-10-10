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
from typing import Annotated

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PLACEHOLDER_SECRET = "generate_a_unique_64_byte_secret_before_running"
REPO_ROOT = Path(__file__).resolve().parents[3]


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

    database_url: str | None = None
    test_database_url: str | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Redis -------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

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
        default_factory=lambda: ["http://localhost:3000", "http://localhost:3001"]
    )

    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10
    rate_limit_report_per_minute: int = 12

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

    # --- Media -------------------------------------------------------------
    media_storage_backend: str = "local"
    media_storage_path: Path = Path("./storage/media")
    media_max_bytes: int = 10 * 1024 * 1024
    media_allowed_mime: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )

    # --- Geospatial --------------------------------------------------------
    geo_srid: int = 4326
    geo_max_search_radius_km: float = 50.0
    geo_bbox_min_lat: float = 6.0
    geo_bbox_max_lat: float = 37.5
    geo_bbox_min_lon: float = 68.0
    geo_bbox_max_lon: float = 97.5

    # --- AI (Phase 6+) -----------------------------------------------------
    ai_enabled: bool = False
    ai_provider: str | None = None
    ai_api_key: SecretStr | None = None
    ai_model: str | None = None
    ai_timeout_seconds: int = 20

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
    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

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
        if "*" in self.cors_origins:
            problems.append("RAKSHA_CORS_ORIGINS must not contain '*'")
        if not self.cors_origins:
            problems.append("RAKSHA_CORS_ORIGINS must list the allowed origins")
        if any(origin.startswith("http://") for origin in self.cors_origins):
            problems.append("RAKSHA_CORS_ORIGINS must use https outside development")

        if problems:
            raise RuntimeError(
                "Unsafe configuration for environment "
                f"'{self.environment}':\n  - " + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


def generate_secret_key() -> str:
    """Helper used by ``scripts/`` to mint a development secret."""
    return secrets.token_urlsafe(64)


def generate_encryption_key() -> str:
    """A fresh Fernet key (urlsafe base64 of 32 random bytes)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
