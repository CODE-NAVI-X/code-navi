"""Pydantic schemas for the unified portraits overview read endpoint (contract §4.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LearningMasteryOverview(BaseModel):
    """Aggregated quiz mastery facts for the learning portrait."""

    graded_attempts: int = Field(
        ...,
        ge=0,
        description="Total count of graded quiz attempts.",
    )
    strong_points: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Knowledge points with strong mastery (quiz_rate >= 75%, <=5 items).",
    )
    weak_points: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Knowledge points needing review (quiz_rate < 60%, <=5 items).",
    )
    insufficient_sample: bool = Field(
        ...,
        description="True if all knowledge points have fewer than MIN_MASTERY_SAMPLE attempts.",
    )


class LearningReviewQueueOverview(BaseModel):
    """Aggregated self-reported confusion marks for the review queue."""

    active_confusion_marks: int = Field(
        ...,
        ge=0,
        description="Total distinct active 'confused' marks across surfaces.",
    )
    top_surfaces: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Top learning surfaces carrying active confusion marks (<=3).",
    )


class LearningKnowledgeGapOverview(BaseModel):
    """One traceable review item projected from existing Learning/Practice facts."""

    knowledge_point: str = Field(
        ...,
        description="Knowledge focus derived from an existing field.",
    )
    source_type: str = Field(
        ...,
        description=(
            "Stable source kind: quiz_attempt | confusion_mark | practice_outcome "
            "| code_fill_attempt."
        ),
    )
    summary: str = Field(
        ...,
        description="Privacy-safe source summary.",
    )


class LearningPortraitOverview(BaseModel):
    """The learning slice of the unified overview."""

    mastery: LearningMasteryOverview
    review_queue: LearningReviewQueueOverview
    knowledge_gaps: list[LearningKnowledgeGapOverview] = Field(
        default_factory=list,
        max_length=8,
        description="Recent traceable knowledge gaps (<=8).",
    )


class ResearchConversationOverview(BaseModel):
    """Fact projection of one research conversation."""

    conversation_id: str = Field(
        ...,
        description="Research conversation UUID.",
    )
    topic: str | None = Field(
        default=None,
        description="Current research topic.",
    )
    updated_at: str = Field(
        ...,
        description="ISO-8601 timestamp of the conversation's last update.",
    )
    readiness: str | None = Field(
        default=None,
        description="Current readiness stage or evaluation score display (e.g. X/12).",
    )
    evidence_bundle_count: int = Field(
        ...,
        ge=0,
        description="Number of saved evidence bundles in this conversation.",
    )
    reproduction_pipeline_status: str | None = Field(
        default=None,
        description=(
            "Status of the latest reproduction pipeline (evidence_linked | not_started | None)."
        ),
    )


class ResearchPortraitOverview(BaseModel):
    """The research slice of the unified overview."""

    conversations: list[ResearchConversationOverview] = Field(
        default_factory=list,
        description="Recent research conversations (<=conversation_limit).",
    )


class LearningToResearchBridge(BaseModel):
    """Status projection of learning-to-research context handoff."""

    latest_transfer_id: str | None = Field(
        default=None,
        description="Identifier of the latest context transfer draft or confirmed record.",
    )
    confirmed: bool = Field(
        default=False,
        description="Whether the latest transfer has been confirmed.",
    )
    has_mastery_snapshot: bool = Field(
        default=False,
        description="Whether the confirmed context carries a learning mastery snapshot.",
    )


class ResearchToLearningBridge(BaseModel):
    """Status projection of research-to-learning study guidance."""

    pending_study_recommendations: int = Field(
        default=0,
        ge=0,
        description="Number of pending study recommendations derived from the latest conversation.",
    )


class BridgesPortraitOverview(BaseModel):
    """The cross-module bridges slice of the unified overview."""

    learning_to_research: LearningToResearchBridge
    research_to_learning: ResearchToLearningBridge


class PortraitsOverviewResponse(BaseModel):
    """The unified read-only portrait overview (contract §4.1)."""

    profile_id: str = Field(
        ...,
        description="The unified profile key (UUID v4).",
    )
    learning: LearningPortraitOverview
    research: ResearchPortraitOverview
    bridges: BridgesPortraitOverview
    generated_by: Literal["rules"] = Field(
        default="rules",
        description="Static fact indicating rules-only deterministic generation.",
    )
    generated_at: str = Field(
        ...,
        description="ISO-8601 snapshot timestamp.",
    )


__all__ = [
    "BridgesPortraitOverview",
    "LearningKnowledgeGapOverview",
    "LearningMasteryOverview",
    "LearningPortraitOverview",
    "LearningReviewQueueOverview",
    "LearningToResearchBridge",
    "PortraitsOverviewResponse",
    "ResearchConversationOverview",
    "ResearchPortraitOverview",
    "ResearchToLearningBridge",
]
