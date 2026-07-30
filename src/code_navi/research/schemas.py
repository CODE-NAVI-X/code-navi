"""Public request and response schemas for research clarification."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ResearchState(BaseModel):
    """The five fixed fields that must be collected before completion."""

    research_domain: str | None = None
    core_question: str | None = None
    data_and_method: str | None = None
    constraints: str | None = None
    expected_deliverable: str | None = None


class ResearchBrief(ResearchState):
    """Completed, structured research brief produced only by rules."""


class ResearchPlanEntry(BaseModel):
    """One plan entry labelled as a suggestion or an item that needs verification."""

    content: str
    classification: Literal["inference", "to_verify"]
    basis: str


class ResearchPlanRisk(BaseModel):
    """A stated delivery risk and a corresponding non-factual mitigation suggestion."""

    risk: ResearchPlanEntry
    mitigation: ResearchPlanEntry


class ResearchPlan(BaseModel):
    """Rules-only plan derived from a completed brief, never from external evidence."""

    research_title: ResearchPlanEntry
    research_goal: ResearchPlanEntry
    candidate_methods_or_baselines: list[ResearchPlanEntry]
    suggested_datasets_or_metrics: list[ResearchPlanEntry]
    two_week_mvp_plan: list[ResearchPlanEntry]
    risks_and_mitigations: list[ResearchPlanRisk]
    suggested_search_keywords: list[str]
    provenance_note: str


class EvidenceStatement(BaseModel):
    """A claim explicitly labelled by the strength of its source support."""

    content: str
    classification: Literal["fact", "inference", "to_verify"]
    source_url: str | None = None
    basis: str


class AcademicSourceStatus(BaseModel):
    source: str
    status: Literal[
        "success",
        "no_results",
        "network_error",
        "timeout",
        "unavailable",
        "disabled",
        "not_allowed",
        "dependency_missing",
    ]
    source_url: str | None = None
    accessed_at: datetime
    reason: str | None = None


class AcademicPaperResult(BaseModel):
    title: str
    authors: list[str]
    year: int | None = None
    source_name: str
    url: str
    identifier: str | None = None
    abstract_excerpt: str | None = None
    accessed_at: datetime
    information_scope: Literal["metadata_and_abstract_only"]
    metadata_evidence: list[EvidenceStatement]
    supporting_snippets: list[EvidenceStatement]
    relevance: EvidenceStatement
    verification: EvidenceStatement
    full_text_available: Literal[False]


class EvidenceBundle(BaseModel):
    """Traceable, metadata-only evidence returned by one explicit search action."""

    session_id: str
    query: str
    allowed_sources: list[str]
    queried_sources: list[str]
    source_statuses: list[AcademicSourceStatus]
    searched_at: datetime
    papers: list[AcademicPaperResult]
    source_links: list[str | None]
    failure_reasons: list[str]
    provenance_note: str
    tool_audit: dict[str, object] | None = None


class ClarificationQuestion(BaseModel):
    """One deterministic question and its three recommended responses."""

    field: str
    label: str
    question: str
    options: list[str] = Field(min_length=3, max_length=3)


class ResearchTurn(BaseModel):
    """Persisted user response used to make a session auditable and resumable."""

    field: str
    value: str
    input_mode: str
    recorded_at: datetime


class CreateResearchSessionRequest(BaseModel):
    """Optional initial description, treated as the first free-text response."""

    initial_description: str | None = Field(default=None, max_length=500)


class SubmitResearchTurnRequest(BaseModel):
    """A user may choose one recommended option or provide free text."""

    answer: str | None = Field(default=None, max_length=500)
    selected_option: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_exactly_one_response(self) -> SubmitResearchTurnRequest:
        values = [value for value in (self.answer, self.selected_option) if value and value.strip()]
        if len(values) != 1:
            raise ValueError("Provide exactly one of answer or selected_option.")
        return self


class CreateEvidenceBundleRequest(BaseModel):
    """Explicit user search request; no endpoint performs automatic network calls."""

    query: str | None = Field(default=None, min_length=2, max_length=300)
    sources: list[Literal["arxiv"]] = Field(
        default_factory=lambda: ["arxiv"], min_length=1, max_length=1
    )


class ResearchSessionResponse(BaseModel):
    """Stable API response for creation, progression, and restoration."""

    session_id: str
    state: ResearchState
    missing_fields: list[str]
    next_question: ClarificationQuestion | None
    completed: bool
    reply: str
    generation_mode: Literal["rules", "llm", "rules_fallback"]
    research_brief: ResearchBrief | None = None
    research_plan: ResearchPlan | None = None
    turns: list[ResearchTurn]
