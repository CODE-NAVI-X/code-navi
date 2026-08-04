"""Public schemas for conversational research clarification."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schemas import AcademicPaperResult, AcademicSourceStatus

ProfileField = Literal[
    "topic",
    "motivation",
    "research_questions",
    "candidate_questions",
    "context",
    "methods",
    "data_requirements",
    "evidence_preferences",
    "time_scope",
    "constraints",
    "expected_output",
]


class ResearchProfile(BaseModel):
    """Evolving research understanding assembled from the conversation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str | None = Field(default=None, min_length=1, max_length=500)
    motivation: str | None = Field(default=None, min_length=1, max_length=1000)
    research_questions: list[str] = Field(default_factory=list, max_length=8)
    candidate_questions: list[str] = Field(default_factory=list, max_length=8)
    context: str | None = Field(default=None, min_length=1, max_length=1000)
    methods: list[str] = Field(default_factory=list, max_length=12)
    data_requirements: str | None = Field(default=None, min_length=1, max_length=1000)
    evidence_preferences: list[str] = Field(default_factory=list, max_length=12)
    time_scope: str | None = Field(default=None, min_length=1, max_length=300)
    constraints: list[str] = Field(default_factory=list, max_length=12)
    expected_output: str | None = Field(default=None, min_length=1, max_length=500)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    uncertainties: list[str] = Field(default_factory=list, max_length=12)

    @field_validator(
        "research_questions",
        "candidate_questions",
        "methods",
        "evidence_preferences",
        "constraints",
        "assumptions",
        "uncertainties",
    )
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        """Trim, de-duplicate, and reject blank list entries."""
        normalized: list[str] = []
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("list entries must not be blank")
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized


class ResearchProfilePatch(BaseModel):
    """Validated partial update proposed by one conversation turn."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str | None = Field(default=None, min_length=1, max_length=500)
    motivation: str | None = Field(default=None, min_length=1, max_length=1000)
    research_questions: list[str] | None = Field(default=None, max_length=8)
    context: str | None = Field(default=None, min_length=1, max_length=1000)
    methods: list[str] | None = Field(default=None, max_length=12)
    data_requirements: str | None = Field(default=None, min_length=1, max_length=1000)
    evidence_preferences: list[str] | None = Field(default=None, max_length=12)
    time_scope: str | None = Field(default=None, min_length=1, max_length=300)
    constraints: list[str] | None = Field(default=None, max_length=12)
    expected_output: str | None = Field(default=None, min_length=1, max_length=500)
    clear_fields: list[ProfileField] = Field(default_factory=list, max_length=11)

    @field_validator(
        "research_questions",
        "methods",
        "evidence_preferences",
        "constraints",
    )
    @classmethod
    def normalize_patch_lists(cls, values: list[str] | None) -> list[str] | None:
        """Reject blank model patch values before they reach persistence."""
        return None if values is None else ResearchProfile.normalize_list(values)

    @field_validator("clear_fields")
    @classmethod
    def normalize_clear_fields(cls, values: list[ProfileField]) -> list[ProfileField]:
        """Apply every explicit clear at most once."""
        return list(dict.fromkeys(values))


class ResearchConversationDecision(BaseModel):
    """Only model decision shape accepted by the application service."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reply: str = Field(min_length=1, max_length=1500)
    intent: Literal[
        "explore",
        "clarify",
        "correct",
        "compare",
        "summarize",
        "prepare_search",
    ]
    profile_patch: ResearchProfilePatch = Field(default_factory=ResearchProfilePatch)
    candidate_questions: list[str] = Field(default_factory=list, max_length=5)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    next_question: str | None = Field(default=None, min_length=1, max_length=500)
    suggested_answers: list[str] = Field(default_factory=list, max_length=4)
    recommended_action: Literal[
        "continue_dialogue",
        "review_profile",
        "prepare_search",
    ] = "continue_dialogue"

    @field_validator(
        "candidate_questions", "assumptions", "uncertainties", "suggested_answers"
    )
    @classmethod
    def normalize_decision_lists(cls, values: list[str]) -> list[str]:
        """Keep assistant-facing suggestions non-empty and unique."""
        return ResearchProfile.normalize_list(values)


class ResearchConversationMessage(BaseModel):
    """One persisted user or assistant message with optional audit metadata."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    created_at: datetime
    generation_mode: Literal["agent", "rules", "rules_fallback"] | None = None
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)
    intent: str | None = None
    next_question: str | None = None
    suggested_answers: list[str] = Field(default_factory=list)
    candidate_questions: list[str] = Field(default_factory=list)
    recommended_action: Literal[
        "continue_dialogue",
        "review_profile",
        "prepare_search",
    ] | None = None


class ResearchReadiness(BaseModel):
    """Explainable readiness estimate; it is not a fixed completion gate."""

    score: int = Field(ge=0, le=100)
    stage: Literal["exploring", "focusing", "ready_for_plan"]
    can_prepare_search: bool
    reasons: list[str]


PlanClassification = Literal["inference", "to_verify"]


class ResearchPlanEntry(BaseModel):
    """One bounded, non-factual recommendation in a conversation research plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=1000)
    classification: PlanClassification
    basis: str = Field(min_length=1, max_length=1000)


class ResearchPlanRisk(BaseModel):
    """A risk and its proposed mitigation, both clearly labelled as suggestions."""

    model_config = ConfigDict(extra="forbid")

    risk: ResearchPlanEntry
    mitigation: ResearchPlanEntry


class ConversationResearchPlan(BaseModel):
    """Offline, restorable plan derived only from an already validated profile."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["research-plan.v1"] = "research-plan.v1"
    research_title: ResearchPlanEntry
    research_goal: ResearchPlanEntry
    candidate_methods_or_baselines: list[ResearchPlanEntry] = Field(min_length=1)
    suggested_datasets_or_metrics: list[ResearchPlanEntry] = Field(min_length=1)
    two_week_mvp_plan: list[ResearchPlanEntry] = Field(min_length=1)
    risks_and_mitigations: list[ResearchPlanRisk] = Field(min_length=1)
    suggested_search_keywords: list[str] = Field(min_length=1, max_length=8)
    pending_items: list[ResearchPlanEntry] = Field(default_factory=list)
    provenance_note: str = Field(min_length=1, max_length=1000)


class CreateResearchConversationRequest(BaseModel):
    """Create a conversation, optionally processing the first user message."""

    model_config = ConfigDict(extra="forbid")

    initial_message: str | None = Field(default=None, max_length=4000)

    @field_validator("initial_message")
    @classmethod
    def initial_message_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("initial_message must not be blank")
        return value.strip() if value else None


class SendResearchMessageRequest(BaseModel):
    """Submit one free-form message to an existing research conversation."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message must not be blank")
        return cleaned


class ResearchConversationResponse(BaseModel):
    """Restorable conversational state returned by create, send, and get."""

    schema_version: Literal["research-conversation.v1"] = "research-conversation.v1"
    active_skill: Literal["research-clarification"] = "research-clarification"
    next_skill: Literal["academic-search"] | None = None
    conversation_id: str
    profile: ResearchProfile
    readiness: ResearchReadiness
    stage: Literal["exploring", "focusing", "ready_for_plan"]
    ready_for_plan: bool
    research_plan: ConversationResearchPlan | None = None
    reply: str
    generation_mode: Literal["agent", "rules", "rules_fallback"]
    recommended_action: Literal[
        "continue_dialogue",
        "review_profile",
        "prepare_search",
    ]
    next_question: str | None
    suggested_answers: list[str]
    candidate_questions: list[str]
    messages: list[ResearchConversationMessage]
    last_run_id: str | None = None


class ResearchSearchSource(BaseModel):
    """One allow-listed source offered by the academic-search Skill."""

    id: Literal["arxiv", "openalex", "crossref"]
    display_name: str
    homepage: str
    enabled: bool = True
    scope: str


class ResearchSearchPlan(BaseModel):
    """Deterministic, reviewable plan prepared before any network request."""

    schema_version: Literal["research-search-plan.v1"] = "research-search-plan.v1"
    conversation_id: str
    query: str = Field(min_length=2, max_length=300)
    alternative_queries: list[str] = Field(default_factory=list, max_length=4)
    sources: list[ResearchSearchSource]
    evidence_scope: Literal["metadata_and_abstract_only"] = "metadata_and_abstract_only"
    user_confirmation_required: Literal[True] = True
    provenance_note: str


class CreateConversationEvidenceBundleRequest(BaseModel):
    """Explicit user confirmation for one source-restricted search run."""

    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, min_length=2, max_length=300)
    sources: list[Literal["arxiv", "openalex", "crossref"]] = Field(
        default_factory=lambda: ["openalex", "crossref", "arxiv"],
        min_length=1,
        max_length=3,
    )


class ConversationEvidenceBundle(BaseModel):
    """Traceable evidence collected for the conversational research workflow."""

    schema_version: Literal["academic-evidence.v1"] = "academic-evidence.v1"
    bundle_id: str
    conversation_id: str
    query: str
    requested_sources: list[str]
    allowed_sources: list[str]
    queried_sources: list[str]
    source_statuses: list[AcademicSourceStatus]
    searched_at: datetime
    papers: list[AcademicPaperResult]
    source_links: list[str | None]
    failure_reasons: list[str]
    provenance_note: str
    tool_audit: dict[str, object] | None = None
    cache_hit: bool = False
