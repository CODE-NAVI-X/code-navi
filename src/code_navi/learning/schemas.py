"""Pydantic request / response data-models for the learning module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Citation(BaseModel):
    """A single source citation attached to an explanation snippet."""

    source_title: str = Field(
        ...,
        description="Human-readable title of the cited source (e.g. RFC, textbook, commit).",
    )
    uri: str | None = Field(
        default=None,
        description="Resolvable URL / DOI / permalink to the source.",
    )
    snippet: str | None = Field(
        default=None,
        description="Short verbatim excerpt that supports the explanation.",
    )


class ExplainRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/explain``."""

    knowledge_point: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "The knowledge-point identifier, question, or source-material excerpt to explain."
        ),
    )
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Client-owned learning session. Omit to have the server mint one; "
            "reuse the returned value to keep notebook entries grouped."
        ),
    )
    persona: str | None = Field(
        default="academic",
        description="Student persona controlling depth & tone of the explanation.",
    )
    include_citations: bool = Field(
        default=True,
        description="Whether the response should include source citations.",
    )
    local_profile_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Browser-local Workspace scope. It only isolates local product data and "
            "does not represent authentication or authorization."
        ),
    )
    workspace_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
        description="Optional persisted Workspace that owns the derived Learning Activity.",
    )
    task_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
        description="Optional Task that owns the derived Learning Activity.",
    )

    @model_validator(mode="after")
    def require_profile_for_workspace_context(self) -> ExplainRequest:
        if (self.workspace_id or self.task_id) and not self.local_profile_id:
            raise ValueError("local_profile_id is required when Workspace context is provided.")
        return self


class ExplainResponse(BaseModel):
    """Response returned after explaining a knowledge point."""

    knowledge_point: str = Field(
        ..., description="Echoed knowledge-point identifier from the request."
    )
    session_id: str = Field(
        ...,
        description="Effective session identifier; persist it to scope later notebook reads.",
    )
    notebook_item_id: str | None = Field(
        default=None,
        description=(
            "Id of the archived summary notebook item backing this explanation; "
            "the client uses it to open the learning → research context-transfer "
            "confirm flow for this exact record."
        ),
    )
    summary: str = Field(..., description="Concise explanation of the knowledge point.")
    detail: str | None = Field(
        default=None,
        description="Extended explanation with deeper context.",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Ordered list of source citations backing the explanation.",
    )


class RecentLearningItem(BaseModel):
    """A bounded, profile-scoped Learning result that can be restored in the Web UI."""

    id: str
    knowledge_point: str
    session_id: str | None = None
    notebook_item_id: str | None = None
    summary: str | None = None
    detail: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime
    status: Literal["available", "source_unavailable"]


class RecentLearningListResponse(BaseModel):
    items: list[RecentLearningItem]
