"""Pydantic request / response data-models for the learning module."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
        max_length=512,
        description="The knowledge-point identifier or free-text query to explain.",
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
