"""Public schemas for pure-rule research guidance endpoints (contract §2.1/§2.2).

These projections never call a model and never touch the network; every field is
derived by rules from already persisted conversation state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .conversation_schemas import EvidenceReference


class StageBriefingKnowledgePoint(BaseModel):
    """One knowledge point surfaced from the confirmed learning mastery snapshot."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    mastery: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Snapshot stores strong/weak lists only; rules never invent numbers.",
    )


class StageBriefingSummary(BaseModel):
    """Learning background summary projected from the confirmed context snapshot."""

    model_config = ConfigDict(extra="forbid")

    topic: str | None = Field(default=None, max_length=500)
    digest: str | None = Field(default=None, max_length=1000)
    knowledge_points: list[StageBriefingKnowledgePoint] | None = Field(
        default=None,
        max_length=8,
    )


class StageBriefingReproductionEntry(BaseModel):
    """Entry point for the paper reproduction path of this conversation."""

    model_config = ConfigDict(extra="forbid")

    bundle_count: int = Field(ge=0)
    pipeline_status: str | None = Field(default=None, max_length=100)


class StageBriefingEvidenceTrend(BaseModel):
    """One rule-aggregated direction hint over this conversation's saved evidence."""

    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(min_length=1, max_length=100)
    paper_count: int = Field(ge=1)
    evidence_refs: list[EvidenceReference] = Field(max_length=5)


class StageBriefingResponse(BaseModel):
    """Response of ``GET .../stage-briefing`` (contract §2.1)."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=36)
    has_learning_context: bool
    stage_summary: StageBriefingSummary
    reproduction_entry: StageBriefingReproductionEntry
    evidence_trends: list[StageBriefingEvidenceTrend] = Field(
        default_factory=list,
        max_length=3,
    )
    generated_by: Literal["rules"] = "rules"
    generated_at: datetime


class StudyRecommendationRequest(BaseModel):
    """Explicit-trigger request for ``POST .../study-recommendations``."""

    model_config = ConfigDict(extra="forbid")

    user_confirmed: bool = False


class StudyRecommendationAction(BaseModel):
    """Jump payload directly submittable to the learning explain or §1.2 endpoint."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["learning_explain", "practice_set"]
    payload: dict[str, object]


class StudyRecommendation(BaseModel):
    """One rule-extracted knowledge point to learn for the research at hand."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    knowledge_point: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=300)
    mastery_status: Literal["mastered", "weak", "unknown"]
    action: StudyRecommendationAction


class StudyRecommendationsResponse(BaseModel):
    """Response of ``POST .../study-recommendations`` (contract §2.2)."""

    model_config = ConfigDict(extra="forbid")

    recommendations: list[StudyRecommendation] = Field(max_length=6)
    provenance_note: str = Field(min_length=1, max_length=1000)


__all__ = [
    "StageBriefingEvidenceTrend",
    "StageBriefingKnowledgePoint",
    "StageBriefingReproductionEntry",
    "StageBriefingResponse",
    "StageBriefingSummary",
    "StudyRecommendation",
    "StudyRecommendationAction",
    "StudyRecommendationRequest",
    "StudyRecommendationsResponse",
]
