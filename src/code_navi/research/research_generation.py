"""Typed failures for provider-generated research content."""

from __future__ import annotations

from typing import Literal

from .research_artifact_llm import ArtifactLlmOutcome

ResearchGenerationStage = Literal["provider_unavailable", "timeout", "invalid_output", "failed"]


class ResearchGenerationError(RuntimeError):
    """A generated research artefact failed; rules never substitute prose."""

    def __init__(self, stage: ResearchGenerationStage, detail: str) -> None:
        super().__init__(detail)
        self.stage = stage
        self.detail = detail


def require_generated_artifact(outcome: ArtifactLlmOutcome, *, kind: str) -> str:
    """Normalize provider output into JSON text or raise a typed generation error."""
    if outcome.status == "unavailable":
        raise ResearchGenerationError(
            "provider_unavailable",
            f"{kind}: research model provider is not configured",
        )
    if outcome.status != "generated" or not outcome.text:
        stage: ResearchGenerationStage = "failed"
        detail = outcome.reason or "no output"
        if "timed out" in detail or "timeout" in detail:
            stage = "timeout"
        raise ResearchGenerationError(stage, f"{kind}: {detail}")
    return outcome.text
