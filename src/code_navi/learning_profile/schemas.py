"""Pydantic models for the learning portrait and confusion marks.

The portrait is anonymous and keyed by ``profile_id`` (== the practice
``learner_id`` UUID).  It aggregates real persisted scores only — every
``quiz_rate`` / ``mastery`` value below is computed from ``quiz_attempts``
rows, never invented by an LLM.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: UUID v4 — the unified profile key format (same as the quiz grade request).
UUID_V4_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

#: Learning surfaces that can carry a "看不懂/懂了" mark.
MarkSourceType = Literal["ppt_page", "explain", "quiz_question"]

#: Minimum graded attempts before a mastery value is reported.  Below this the
#: portrait says 样本不足 (``mastery=None``) instead of showing a fake number.
MIN_MASTERY_SAMPLE = 3


class MarkRequest(BaseModel):
    """Binary toggle of a self-reported "看不懂/懂了" mark on one surface.

    ``knowledge_point`` is the semantic, free-text knowledge name — a mark
    survives PPT regeneration / quiz re-making because the portrait aggregates
    by this name, not by ``source_ref``.  ``source_ref`` keeps traceability to
    the exact entity (e.g. ``presentation_id:slide_idx``, a term, a question id).
    """

    session_id: str = Field(
        ..., min_length=1, max_length=64, description="Learning session scope."
    )
    profile_id: str | None = Field(
        default=None,
        pattern=UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Optional unified profile key (== the practice learner_id UUID).",
    )
    knowledge_point: str = Field(
        ..., min_length=1, max_length=512, description="Semantic knowledge name."
    )
    source_type: MarkSourceType = Field(
        ..., description="ppt_page | explain | quiz_question."
    )
    source_ref: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Entity this mark is attached to (traceability only).",
    )
    mark: bool = Field(
        ..., description="True → 看不懂 (confused); False → 懂了 (understood)."
    )


class MarkResponse(BaseModel):
    """Echo after a toggle lands."""

    session_id: str = Field(..., description="Echoed from the request.")
    source_type: MarkSourceType = Field(..., description="Echoed surface type.")
    source_ref: str = Field(..., description="Echoed target entity.")
    status: Literal["confused", "understood"] = Field(
        ..., description="Effective state after the toggle."
    )


class ProfileMastery(BaseModel):
    """One knowledge point's quiz-derived mastery."""

    knowledge_point: str = Field(..., description="Knowledge name.")
    quiz_rate: float | None = Field(
        default=None,
        description="Σscore/Σmax_score over graded attempts; None when none graded.",
    )
    sample_size: int = Field(..., ge=0, description="Graded attempt count.")
    mastery: float | None = Field(
        default=None,
        description=(
            "quiz_rate once sample_size >= MIN_MASTERY_SAMPLE, else None "
            "(样本不足 — never a fabricated number)."
        ),
    )
    status: Literal["sufficient", "insufficient"] = Field(
        ..., description="sufficient only when a real mastery value is reported."
    )


class ConfusionItem(BaseModel):
    """One knowledge point that currently carries ≥1 看不懂 mark."""

    knowledge_point: str = Field(..., description="Knowledge name.")
    mark_count: int = Field(..., ge=1, description="Open 看不懂 marks on it.")
    source_types: list[MarkSourceType] = Field(
        default_factory=list, description="Surfaces that carry those marks."
    )


class ProfileResponse(BaseModel):
    """The aggregated anonymous learning portrait."""

    profile_id: str = Field(..., description="The unified profile key (UUID v4).")
    generated_at: str = Field(..., description="ISO-8601 timestamp of the snapshot.")
    mastery: list[ProfileMastery] = Field(
        default_factory=list, description="Per-knowledge-point quiz mastery."
    )
    strengths: list[str] = Field(
        default_factory=list, description="Knowledge points with strong mastery."
    )
    weaknesses: list[str] = Field(
        default_factory=list, description="Knowledge points that need review."
    )
    confusion: list[ConfusionItem] = Field(
        default_factory=list, description="Knowledge points marked 看不懂."
    )
