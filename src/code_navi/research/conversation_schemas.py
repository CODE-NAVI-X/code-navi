"""Public schemas for conversational research clarification."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from code_navi.context_transfer.schemas import ConfirmedContextProvenance

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

    @field_validator("candidate_questions", "assumptions", "uncertainties", "suggested_answers")
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
    recommended_action: (
        Literal[
            "continue_dialogue",
            "review_profile",
            "prepare_search",
        ]
        | None
    ) = None


class ResearchReadiness(BaseModel):
    """Explainable readiness estimate; it is not a fixed completion gate."""

    score: int = Field(ge=0, le=100)
    stage: Literal["exploring", "focusing", "ready_for_plan"]
    can_prepare_search: bool
    reasons: list[str]


PlanClassification = Literal["inference", "to_verify"]
MindMapNodeStatus = Literal["confirmed", "inference", "to_verify", "evidence", "risk"]


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


class ResearchMindMapSource(BaseModel):
    """One traceable source attached to a mind-map evidence node."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    accessed_at: datetime


class ResearchMindMapNode(BaseModel):
    """A display-safe research concept with an explicit epistemic status."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=500)
    status: MindMapNodeStatus
    detail: str = Field(min_length=1, max_length=1000)
    sources: list[ResearchMindMapSource] = Field(default_factory=list, max_length=6)


class ResearchMindMapEdge(BaseModel):
    """A directed, explainable relationship between two mind-map nodes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    relation: str = Field(min_length=1, max_length=200)


class ResearchMindMap(BaseModel):
    """Offline node-and-edge graph derived from a profile, plan, and saved evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["research-mindmap.v1"] = "research-mindmap.v1"
    root_node_id: str = Field(min_length=1, max_length=100)
    nodes: list[ResearchMindMapNode] = Field(min_length=1, max_length=40)
    edges: list[ResearchMindMapEdge] = Field(default_factory=list, max_length=80)
    provenance_note: str = Field(min_length=1, max_length=1000)


class EvidenceReference(BaseModel):
    """Stable reference to one paper stored in a conversation evidence bundle."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bundle_id: str = Field(min_length=1, max_length=100)
    paper_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=1000)
    source_name: str = Field(min_length=1, max_length=200)
    year: int | None = None
    evidence_level: Literal["metadata", "abstract", "full_text"]
    evidence_summary: str | None = Field(default=None, max_length=1000)


AnalysisClassification = Literal["fact", "inference", "to_verify"]


class ResearchAnalysisItem(BaseModel):
    """One scoped difficulty observation with its epistemic boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    area: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1000)
    source_scope: Literal["profile_and_plan_only", "metadata_and_abstract_only"]
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=8)


class TopicDifficultyAnalysis(BaseModel):
    """Rules-only direction analysis; it does not claim paper-specific findings."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["topic-difficulty-analysis.v1"] = "topic-difficulty-analysis.v1"
    title: str = Field(min_length=1, max_length=500)
    information_scope: Literal["profile_and_plan_only", "metadata_and_abstract_only"]
    items: list[ResearchAnalysisItem] = Field(min_length=1, max_length=12)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)


class PaperAnalysis(BaseModel):
    """Metadata/abstract-only paper analysis returned for an explicitly selected paper."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["paper-analysis.v1"] = "paper-analysis.v1"
    title: str = Field(min_length=1, max_length=1000)
    paper_url: str = Field(min_length=1, max_length=2000)
    information_scope: Literal["metadata_and_abstract_only"] = "metadata_and_abstract_only"
    abstract_available: bool
    items: list[ResearchAnalysisItem] = Field(min_length=1, max_length=12)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)


class ExperimentDesign(BaseModel):
    """Offline experiment suggestions derived from a rules research plan."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["experiment-design.v1"] = "experiment-design.v1"
    hypothesis: ResearchPlanEntry
    variables: list[ResearchPlanEntry] = Field(min_length=1, max_length=6)
    data_sources: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    baselines: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    metrics: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    steps: list[ResearchPlanEntry] = Field(min_length=1, max_length=6)
    resources: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    risks: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    advisor_confirmation_items: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)


class ExperimentCodeDraftFile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=10000)


class ExperimentCodeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["experiment-code-draft.v1"] = "experiment-code-draft.v1"
    title: str = Field(min_length=1, max_length=500)
    directory_tree: list[str] = Field(min_length=1, max_length=20)
    dependencies: list[str] = Field(default_factory=list, max_length=10)
    files: list[ExperimentCodeDraftFile] = Field(min_length=1, max_length=10)
    run_instructions: list[str] = Field(min_length=1, max_length=6)
    assumptions: list[str] = Field(min_length=1, max_length=8)
    to_verify_items: list[str] = Field(min_length=1, max_length=8)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)


class CreateExperimentCodeDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_confirmed: Literal[True]


class GenerateResearchArtifactRequest(BaseModel):
    """Require an explicit user action before an optional model call."""

    model_config = ConfigDict(extra="forbid")

    user_confirmed: Literal[True]


class AnalyzeConversationPaperRequest(BaseModel):
    """Identify a paper already stored in the current conversation's evidence bundles."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_url: str = Field(min_length=1, max_length=2000)


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
    research_mindmap: ResearchMindMap
    topic_difficulty_analysis: TopicDifficultyAnalysis
    experiment_design: ExperimentDesign | None = None
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
    context_provenance: ConfirmedContextProvenance | None = None


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


class SaveResearchNotebookNoteRequest(BaseModel):
    """Save selected evidence into one explicitly chosen Learning notebook."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    learning_session_id: str = Field(min_length=1, max_length=64)
    selected_paper_urls: list[str] = Field(min_length=1, max_length=12)

    @field_validator("selected_paper_urls")
    @classmethod
    def normalize_selected_papers(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("selected_paper_urls must not contain blank values")
        return list(dict.fromkeys(normalized))


class SavedResearchNotebookNote(BaseModel):
    """Identity and provenance for a Research note archived in Learning."""

    schema_version: Literal["research-notebook-note.v1"] = "research-notebook-note.v1"
    notebook_item_id: str
    learning_session_id: str
    conversation_id: str
    bundle_id: str
    research_topic: str
    research_question: str
    evidence_refs: list[EvidenceReference]
    next_steps: list[str]


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
