"""``render.yaml`` against the code it deploys.

Render's own schema could not be fetched from the development environment, so these
checks cover what the repository can know: every variable is one the application reads,
no secret is written into the file, the production configuration it produces passes the
start-up safety check, and every path it names exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

REPO = Path(__file__).resolve().parents[3]
BLUEPRINT: dict[str, Any] = yaml.safe_load((REPO / "render.yaml").read_text())
SERVICE = next(s for s in BLUEPRINT["services"] if s["name"] == "raksha-api")
DATABASES = {db["name"]: db for db in BLUEPRINT["databases"]}
ENV = {var["key"]: var for var in SERVICE["envVars"]}

#: Read by scripts/render_start.sh, not by the application.
START_SCRIPT_VARIABLES = {"FIRST_ADMIN_EMAIL", "FIRST_ADMIN_NAME", "FIRST_ADMIN_PASSWORD"}
SECRETS = {"RAKSHA_SECRET_KEY", "RAKSHA_ENCRYPTION_KEY", "RAKSHA_DATABASE_URL"}


def test_every_application_variable_is_one_the_settings_read() -> None:
    fields = set(Settings.model_fields)
    for key in ENV:
        if key in START_SCRIPT_VARIABLES:
            continue
        assert key.startswith("RAKSHA_"), key
        assert key.removeprefix("RAKSHA_").lower() in fields, f"{key} is not a setting"


@pytest.mark.parametrize("key", sorted(SECRETS | START_SCRIPT_VARIABLES))
def test_no_secret_or_personal_value_is_written_into_the_file(key: str) -> None:
    var = ENV[key]
    assert "value" not in var, f"{key} must be generated, linked or entered on Render"
    assert var.get("generateValue") or var.get("fromDatabase") or var.get("sync") is False


def test_the_database_link_points_at_a_database_in_the_same_region() -> None:
    link = ENV["RAKSHA_DATABASE_URL"]["fromDatabase"]
    assert link["property"] == "connectionString"
    database = DATABASES[link["name"]]
    assert database["region"] == SERVICE["region"]  # internal connection only
    assert database["ipAllowList"] == []
    assert str(database["postgresMajorVersion"]) == "16"


def test_the_configuration_it_produces_passes_the_production_safety_check() -> None:
    literal = {
        key.removeprefix("RAKSHA_").lower(): var["value"]
        for key, var in ENV.items()
        if key.startswith("RAKSHA_") and "value" in var
    }
    settings = Settings(
        **literal,
        # Stand-ins for what Render generates or links (shape, not value).
        secret_key="g" * 44,
        encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        database_url="postgres://raksha:pw@raksha-db:5432/raksha_net_ai",
    )
    settings.assert_safe_for_environment()
    assert settings.environment.value == "production"
    assert settings.trusted_proxy_hops == 1
    assert all(origin.startswith("https://") for origin in settings.cors_origins)


def test_the_paths_it_names_exist() -> None:
    assert (REPO / SERVICE["dockerfilePath"]).is_file()
    assert SERVICE["dockerContext"] == "."  # the Dockerfile copies backend/ and ai/
    script = SERVICE["dockerCommand"].split()[-1]
    # backend/ is copied to /app in the image.
    assert (REPO / "backend" / script.removeprefix("/app/")).is_file()


def test_the_health_check_path_answers_without_a_database() -> None:
    with TestClient(create_app()) as client:
        assert client.get(SERVICE["healthCheckPath"]).status_code == 200
