"""Loads an operator-supplied priority configuration from a JSON file.

This is the one place besides ``app.core.config`` that reads from disk for the
priority engine, exactly as ``media_service`` reads a configured path for
uploads (``CLAUDE.md`` section 4, rule 8: configuration comes from the
environment; the *path* is the environment variable, what is at that path is
this module's job to read). The engine itself (``engine.py``) never touches a
file — it only ever receives an already-built, immutable :class:`PriorityWeights`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import IncidentCategory, PriorityBand, SeverityLevel
from app.services.priority.engine import (
    PriorityWeights,
    register_weights,
    resolve_weights,
)

logger = get_logger(__name__)


class PriorityWeightsFile(BaseModel):
    """The on-disk shape of a custom configuration. Validated, not trusted."""

    model_config = ConfigDict(extra="forbid")

    version: str
    band_thresholds: list[tuple[int, PriorityBand]]
    category_base_score: dict[IncidentCategory, int]
    default_category_score: int
    severity_score: dict[SeverityLevel, int]
    people_trapped_score: int
    immediate_danger_score: int
    medical_required_score: int
    people_affected_per_person: float
    people_affected_cap: int
    people_affected_sanity_limit: int
    age_score_per_15_min: int
    age_score_cap: int

    def to_weights(self) -> PriorityWeights:
        return PriorityWeights(
            version=self.version,
            band_thresholds=tuple(self.band_thresholds),
            category_base_score=dict(self.category_base_score),
            default_category_score=self.default_category_score,
            severity_score=dict(self.severity_score),
            people_trapped_score=self.people_trapped_score,
            immediate_danger_score=self.immediate_danger_score,
            medical_required_score=self.medical_required_score,
            people_affected_per_person=self.people_affected_per_person,
            people_affected_cap=self.people_affected_cap,
            people_affected_sanity_limit=self.people_affected_sanity_limit,
            age_score_per_15_min=self.age_score_per_15_min,
            age_score_cap=self.age_score_cap,
        )


def register_weights_file(path: Path) -> None:
    """Parse ``path`` and register the configuration it describes.

    Raises on a missing, malformed, or invalid file — a priority configuration
    that fails to load must stop the deployment from starting with the wrong
    one silently in effect, not fall back quietly.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    weights = PriorityWeightsFile.model_validate(raw).to_weights()
    register_weights(weights)
    logger.info(
        "priority_weights_registered",
        extra={"version": weights.version, "source": str(path)},
    )


def load_active_weights(settings: Settings) -> PriorityWeights:
    """Register any configured file, then resolve the deployment's active version.

    Safe to call more than once (e.g. once at startup and again per service
    instantiation): re-registering the same version with identical values is a
    no-op; the file is simply re-read and re-validated.
    """
    if settings.priority_weights_path is not None:
        register_weights_file(settings.priority_weights_path)
    return resolve_weights(settings.priority_weights_version)
