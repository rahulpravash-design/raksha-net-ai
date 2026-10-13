"""Text analysis plus photo observations, as one proposal (Phase 8).

The text analyzer produces the structured proposal; the image observer adds observations
from the report's photographs. They fail independently: photographs that cannot be
analysed leave the text proposal intact, with a reasoning factor saying so, because a
dispatcher is better served by half an analysis that says what is missing than by none.
"""

from __future__ import annotations

import time

from ai.common.interfaces import (
    EmergencyAnalyzer,
    ImageObserver,
    ObservationUnavailable,
)
from ai.common.schemas import AnalysisRequest, AnalysisResult


class CompositeAnalyzer:
    def __init__(self, text: EmergencyAnalyzer, images: ImageObserver) -> None:
        self.text = text
        self.images = images
        self.name = f"{text.name}+{images.name}"
        self.version = f"{text.version}+{images.version}"

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        result = self.text.analyze(request)
        if not request.image_bytes:
            return result

        started = time.monotonic()
        try:
            observations = self.images.observe(request.image_bytes)
        except ObservationUnavailable as exc:
            return result.model_copy(
                update={
                    "reasoning_factors": [
                        *result.reasoning_factors,
                        f"Photographs were not analysed: {exc}",
                    ]
                }
            )
        elapsed_ms = int((time.monotonic() - started) * 1000)

        # Traceability (CLAUDE.md section 2, rule 3): the record names both models.
        return result.model_copy(
            update={
                "observations": [*result.observations, *observations],
                "model_name": f"{result.model_name}+{self.images.model}",
                "model_version": f"{result.model_version}+{self.images.version}",
                "provider": self.images.provider,
                "processing_ms": (result.processing_ms or 0) + elapsed_ms,
                "reasoning_factors": [
                    *result.reasoning_factors,
                    f"Photographs examined by {self.images.model}; its observations "
                    "are AI-derived and unverified",
                ],
            }
        )
