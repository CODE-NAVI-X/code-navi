"""Public schemas for conversational research clarification."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from code_navi.context_transfer.schemas import ConfirmedContextProvenance

from .metrics_catalog import TaskType
from .schemas import AcademicPaperResult, AcademicSourceStatus

AreaCode = Literal[
    "research_goal",
    "research_motivation",
    "method_difficulty",
    "data_practice_difficulty",
]

ProfileField = Literal[
    "topic",
    "motivation",
    "research_questions",
    "candidate_questions",
    "context",
    "methods",
    "data_requirements",
    "metrics",
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
    metrics: list[str] = Field(default_factory=list, max_length=8)
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
        "metrics",
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
    metrics: list[str] | None = Field(default=None, max_length=8)
    evidence_preferences: list[str] | None = Field(default=None, max_length=12)
    time_scope: str | None = Field(default=None, min_length=1, max_length=300)
    constraints: list[str] | None = Field(default=None, max_length=12)
    expected_output: str | None = Field(default=None, min_length=1, max_length=500)
    clear_fields: list[ProfileField] = Field(default_factory=list, max_length=12)

    @field_validator(
        "research_questions",
        "methods",
        "metrics",
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
    # Audit metadata written by the orchestrator chat flow.
    triggered_tool: str | None = None
    stage_at_time: str | None = None
    template: str | None = None
    recommended_action: (
        Literal[
            "continue_dialogue",
            "review_profile",
            "prepare_search",
        ]
        | None
    ) = None


class ResearchContextSummary(BaseModel):
    """Persisted coverage boundary for reusable cross-run conversation compression."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["research-context-summary.v1"] = "research-context-summary.v1"
    summary: str = Field(min_length=1, max_length=8000)
    through_message_id: str = Field(min_length=1)
    source_message_count: int = Field(ge=1)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generation_mode: Literal["rules", "agent"]
    run_id: str | None = None


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
    # Evidence-contract fields (checkpoint 3): every recommendation must say
    # why it matters to the current research question and what to do next.
    # Optional so previously stored plans still restore without migration.
    relevance: str | None = Field(default=None, max_length=1000)
    suggested_action: str | None = Field(default=None, max_length=1000)


class ResearchPlanRisk(BaseModel):
    """A risk and its proposed mitigation, both clearly labelled as suggestions."""

    model_config = ConfigDict(extra="forbid")

    risk: ResearchPlanEntry
    mitigation: ResearchPlanEntry


class ConversationResearchPlan(BaseModel):
    """Structured, restorable research plan generated from a validated profile."""

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
    # Evidence contract: top-line verdict and a single highlighted next action.
    core_judgment: str | None = Field(default=None, max_length=1000)
    next_action: str | None = Field(default=None, max_length=1000)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)


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
    # Program-controlled, deterministic link to a paper-analysis section. The
    # model never produces this value; the builder assigns it from a fixed map.
    section_key: str | None = Field(default=None, max_length=100)
    sources: list[ResearchMindMapSource] = Field(default_factory=list, max_length=6)


class ResearchMindMapEdge(BaseModel):
    """A directed, explainable relationship between two mind-map nodes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    relation: str = Field(min_length=1, max_length=200)


class ResearchMindMap(BaseModel):
    """A traceable graph whose wording may be generated after a user request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["research-mindmap.v1"] = "research-mindmap.v1"
    root_node_id: str = Field(min_length=1, max_length=100)
    nodes: list[ResearchMindMapNode] = Field(min_length=1, max_length=40)
    edges: list[ResearchMindMapEdge] = Field(default_factory=list, max_length=80)
    generation_mode: Literal["rules", "llm"] = "rules"
    run_id: str | None = Field(default=None, max_length=200)
    event_count: int = Field(default=0, ge=0, le=10000)
    generated_at: datetime | None = None
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
    # v2 normalized area code (goal, motivation, method, data_practice)
    area_code: AreaCode | None = None
    content: str = Field(min_length=1, max_length=2000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1000)
    source_scope: Literal[
        "profile_and_plan_only",
        "metadata_and_abstract_only",
        "full_text_user_triggered",
    ]
    # Program-derived from ``area`` by a deterministic map; never model-authored.
    section_key: str = Field(default="", max_length=100)
    # Optional paper chapter identity.  When chapter text is available this is
    # validated against the bounded sections supplied to the model.
    chapter_key: str | None = Field(default=None, max_length=50)
    chapter_order: int | None = Field(default=None, ge=1, le=6)
    # Optional capability note generated by rules when mastery snapshot exists
    capability_note: str | None = Field(default=None, max_length=200)
    # Evidence-contract fields (checkpoint 3); optional for stored legacy data.
    relevance: str | None = Field(default=None, max_length=1000)
    suggested_action: str | None = Field(default=None, max_length=1000)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=8)


class TopicDifficultyAnalysis(BaseModel):
    """Rules-only direction analysis; it does not claim paper-specific findings."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["topic-difficulty-analysis.v1"] = "topic-difficulty-analysis.v1"
    title: str = Field(min_length=1, max_length=500)
    information_scope: Literal[
        "profile_and_plan_only", "metadata_and_abstract_only", "full_text_user_triggered"
    ]
    # One-sentence verdict on top plus a single highlighted next action
    # (evidence contract).  Optional so stored legacy analyses still restore.
    core_judgment: str | None = Field(default=None, max_length=1000)
    next_action: str | None = Field(default=None, max_length=1000)
    items: list[ResearchAnalysisItem] = Field(min_length=1, max_length=12)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)


class PaperReadingSection(BaseModel):
    """A recognized paper chapter within the bounded reading excerpt."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=100)
    order: int = Field(ge=1, le=6)
    text: str = Field(max_length=8000)


class PaperReadingEvidence(BaseModel):
    """Provenance for a bounded, user-triggered public PDF read."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["paper-reading.v1"] = "paper-reading.v1"
    source_url: str = Field(min_length=1, max_length=2000)
    page_count: int = Field(ge=1, le=10000)
    pages_read: int = Field(ge=1, le=40)
    text_excerpt: str = Field(min_length=1, max_length=48000)
    sections: list[PaperReadingSection] = Field(default_factory=list, max_length=6)


class PaperAnalysis(BaseModel):
    """Model analysis of a selected paper and optional bounded PDF text."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["paper-analysis.v1"] = "paper-analysis.v1"
    title: str = Field(min_length=1, max_length=1000)
    paper_url: str = Field(min_length=1, max_length=2000)
    information_scope: Literal[
        "metadata_and_abstract_only", "full_text_user_triggered"
    ] = "metadata_and_abstract_only"
    abstract_available: bool
    # Evidence contract: one-sentence verdict, closing summary and a single
    # highlighted next action.  Optional so stored legacy analyses still load.
    core_judgment: str | None = Field(default=None, max_length=1000)
    summary: str | None = Field(default=None, max_length=2000)
    next_action: str | None = Field(default=None, max_length=1000)
    items: list[ResearchAnalysisItem] = Field(min_length=1, max_length=12)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)
    paper_reading: PaperReadingEvidence | None = None


class SelectedResearchPaper(BaseModel):
    """Program-persisted identity for the user's current paper-analysis target."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bundle_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=1000)
    url: str = Field(min_length=1, max_length=2000)
    authors: list[str] = Field(default_factory=list, max_length=100)
    year: int | None = None
    source_name: str = Field(min_length=1, max_length=200)
    doi: str | None = Field(default=None, max_length=300)
    arxiv_id: str | None = Field(default=None, max_length=100)
    abstract_excerpt: str | None = Field(default=None, max_length=5000)
    paper_kind: str | None = Field(default=None, max_length=1000)
    abstract_available: bool


class MetricSpec(BaseModel):
    """Specification for an experiment evaluation metric with verification provenance."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    definition: str = Field(min_length=1, max_length=300)
    formula: str | None = Field(default=None, max_length=300)
    higher_is_better: bool = True
    applies_to_task_type: list[TaskType] = Field(min_length=1)
    source: Literal["standard_catalog", "model_suggested"]
    to_verify: bool


class DatasetRef(BaseModel):
    """Reference to an experiment dataset with accessibility verification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    license_note: str | None = Field(default=None, max_length=200)
    to_verify: bool


class ExperimentDesign(BaseModel):
    """Offline experiment suggestions derived from a rules research plan."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["experiment-design.v1"] = "experiment-design.v1"
    # Task type inferred by rules or overridden by user request (§2.4)
    task_type: TaskType = "other"
    hypothesis: ResearchPlanEntry
    variables: list[ResearchPlanEntry] = Field(min_length=1, max_length=6)
    # v2 structured dataset references and metric specifications (§2.4)
    metric_specs: list[MetricSpec] = Field(default_factory=list, max_length=10)
    dataset_refs: list[DatasetRef] = Field(default_factory=list, max_length=10)
    # Deprecated legacy fields projected from metric_specs and dataset_refs for compatibility
    data_sources: list[ResearchPlanEntry] = Field(default_factory=list, max_length=10)
    baselines: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    metrics: list[ResearchPlanEntry] = Field(default_factory=list, max_length=10)
    steps: list[ResearchPlanEntry] = Field(min_length=1, max_length=6)
    resources: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    risks: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    advisor_confirmation_items: list[ResearchPlanEntry] = Field(min_length=1, max_length=4)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)


UnderstandingCheckStatus = Literal[
    "not_started",
    "question_ready",
    "answer_submitted",
    "needs_explanation",
    "partially_understood",
    "understood",
    "generation_failed",
]

UnderstandingSectionKey = Literal[
    "research_question",
    "core_method",
    "dataset",
    "to_verify",
    "contribution",
    "background",
    "motivation",
    "experiment",
    "metrics",
    "results",
    "limitations",
    "reproduction",
    "other",
]


class CreateUnderstandingQuestionRequest(BaseModel):
    """User explicitly requests one section-bound comprehension question."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_url: str = Field(min_length=1, max_length=2000)
    bundle_id: str = Field(min_length=1, max_length=100)
    section_key: UnderstandingSectionKey


class AssessUnderstandingRequest(BaseModel):
    """User submits their own answer; the program never answers for them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    check_id: str = Field(min_length=1, max_length=100)
    paper_url: str = Field(min_length=1, max_length=2000)
    bundle_id: str = Field(min_length=1, max_length=100)
    section_key: UnderstandingSectionKey
    answer: str = Field(min_length=1, max_length=4000)


class UnderstandingCheck(BaseModel):
    """One evidence-bound comprehension check embedded in paper analysis.

    Identity, ownership, status transitions and timestamps are program-controlled;
    only ``question``, ``assessment``, ``explanation`` and ``example`` are
    model-authored. ``status='understood'`` only means the local check passed —
    it never implies the paper is correct, reproducible, or experimentally verified.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["understanding-check.v1"] = "understanding-check.v1"
    check_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    paper_url: str = Field(min_length=1, max_length=2000)
    bundle_id: str = Field(min_length=1, max_length=100)
    section_key: UnderstandingSectionKey
    question: str = Field(min_length=1, max_length=1000)
    question_basis: str = Field(min_length=1, max_length=1000)
    source_scope: Literal["metadata_only", "metadata_and_abstract_only"]
    answer: str | None = Field(default=None, max_length=4000)
    assessment: str | None = Field(default=None, max_length=2000)
    missing_points: list[str] = Field(default_factory=list, max_length=12)
    correct_points: list[str] = Field(default_factory=list, max_length=12)
    explanation: str | None = Field(default=None, max_length=2000)
    example: str | None = Field(default=None, max_length=2000)
    recommended_next_action: str | None = Field(default=None, max_length=500)
    status: UnderstandingCheckStatus = "not_started"
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "llm"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


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


class GenerateExperimentDesignRequest(BaseModel):
    """Explicit confirmation with optional task type override for experiment design."""

    model_config = ConfigDict(extra="forbid")

    user_confirmed: Literal[True]
    task_type_override: TaskType | None = None


class AnalyzeConversationPaperRequest(BaseModel):
    """Identify a paper already stored in the current conversation's evidence bundles."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_url: str = Field(min_length=1, max_length=2000)
    paper_pdf_url: str | None = Field(default=None, max_length=2000)


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
    research_mindmap: ResearchMindMap | None = None
    selected_paper: SelectedResearchPaper | None = None
    paper_analysis: PaperAnalysis | None = None
    topic_difficulty_analysis: TopicDifficultyAnalysis | None = None
    experiment_design: ExperimentDesign | None = None
    reproduction_conditions: ReproductionConditions | None = None
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


ExperimentEvidenceCategory = Literal[
    "data_or_sample",
    "setup",
    "baseline_or_control",
    "random_seed_or_reason",
    "metric_or_result",
    "result_table",
    "chart_description",
    "failure_or_limitation",
    "ethics_or_data_governance",
    "pending_item",
]


class ExperimentEvidenceItem(BaseModel):
    """One bounded, user-submitted experiment statement and its evidence boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: ExperimentEvidenceCategory
    content: str = Field(min_length=1, max_length=4000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1000)
    source_scope: Literal["user_submitted_text"] = "user_submitted_text"
    related_plan_item: str | None = Field(default=None, max_length=500)
    related_evidence_urls: list[str] = Field(default_factory=list, max_length=8)


class CreateExperimentEvidenceItem(BaseModel):
    """Raw user text. Classification is a reporting boundary, not a system verification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: ExperimentEvidenceCategory
    content: str = Field(min_length=1, max_length=4000)
    classification: AnalysisClassification = "fact"
    related_plan_item: str | None = Field(default=None, max_length=500)
    related_evidence_urls: list[str] = Field(default_factory=list, max_length=8)


class CreateExperimentEvidenceBundleRequest(BaseModel):
    """Explicit, text-only result submission. No local file is read or uploaded."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    experiment_name: str = Field(min_length=1, max_length=500)
    goal: str = Field(min_length=1, max_length=1000)
    items: list[CreateExperimentEvidenceItem] = Field(min_length=1, max_length=30)


class ExperimentEvidenceBundle(BaseModel):
    """Restorable user-reported experimental evidence; it is not independently verified."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["experiment-evidence.v1"] = "experiment-evidence.v1"
    bundle_id: str
    conversation_id: str
    experiment_name: ExperimentEvidenceItem
    goal: ExperimentEvidenceItem
    items: list[ExperimentEvidenceItem] = Field(min_length=1, max_length=30)
    submitted_at: datetime
    provenance_note: str = Field(min_length=1, max_length=1000)


ReproductionTaskStatus = Literal["not_started", "evidence_linked"]


class ReproductionPipelineItem(BaseModel):
    """One reproduction statement with an explicit evidence boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=6000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1000)
    source_scope: str = Field(min_length=1, max_length=300)


class ReproductionSelectedPaper(BaseModel):
    """Identity and available-information boundary for the user-selected source."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=1000)
    source_name: str = Field(min_length=1, max_length=300)
    year: int | None = None
    identifier: str | None = Field(default=None, max_length=500)
    abstract_scope: Literal["metadata_only", "metadata_and_abstract"]
    abstract_excerpt: str | None = Field(default=None, max_length=10000)


class ReproductionTaskEvidenceLink(BaseModel):
    """A user-submitted experimental record associated with one Pipeline task."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    experiment_bundle_id: str = Field(min_length=1, max_length=64)
    source_scope: Literal["user_submitted_text_unverified"] = "user_submitted_text_unverified"
    content: str = Field(min_length=1, max_length=4000)
    classification: AnalysisClassification


class ReproductionTask(BaseModel):
    """A Python-oriented learning task; it is not executable code."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=2000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1000)
    source_scope: str = Field(min_length=1, max_length=300)
    status: ReproductionTaskStatus = "not_started"
    evidence_links: list[ReproductionTaskEvidenceLink] = Field(default_factory=list, max_length=30)


class ReproductionConditions(BaseModel):
    """User-provided reproduction environment, time and goal (checkpoint 4).

    Everything here comes from the user, never from model assumptions; the
    pipeline generation refuses to run until the key conditions are filled.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["reproduction-conditions.v1"] = "reproduction-conditions.v1"
    hardware: str | None = Field(default=None, max_length=500)
    vram: str | None = Field(default=None, max_length=500)
    operating_system: str | None = Field(default=None, max_length=500)
    python_environment: str | None = Field(default=None, max_length=500)
    available_time: str | None = Field(default=None, max_length=500)
    reproduction_goal: str | None = Field(default=None, max_length=1000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReadingReport(BaseModel):
    """The user's own reading summary of a saved paper (checkpoint 5).

    Stored verbatim as user-submitted text; it is never merged into the
    paper-analysis facts and never treated as the paper's own content.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["reading-report.v1"] = "reading-report.v1"
    report_id: str = Field(min_length=8, max_length=64)
    paper_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=8000)
    source_scope: Literal["user_submitted_text_unverified"] = (
        "user_submitted_text_unverified"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReadingReportInput(BaseModel):
    """Request body for submitting a reading report."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=8000)


class ReproductionConditionsInput(BaseModel):
    """Request body for saving user reproduction conditions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hardware: str | None = Field(default=None, max_length=500)
    vram: str | None = Field(default=None, max_length=500)
    operating_system: str | None = Field(default=None, max_length=500)
    python_environment: str | None = Field(default=None, max_length=500)
    available_time: str | None = Field(default=None, max_length=500)
    reproduction_goal: str | None = Field(default=None, max_length=1000)


_REQUIRED_CONDITION_KEYS: tuple[tuple[str, str], ...] = (
    ("hardware", "硬件（GPU/CPU）"),
    ("available_time", "可用时间"),
    ("reproduction_goal", "复现目标"),
)


def missing_required_reproduction_conditions(
    conditions: ReproductionConditions | None,
) -> list[str]:
    """Labels of key conditions the user still has to provide."""
    missing: list[str] = []
    for key, label in _REQUIRED_CONDITION_KEYS:
        value = getattr(conditions, key) if conditions is not None else None
        if not (value or "").strip():
            missing.append(label)
    return missing


class ReproductionPipeline(BaseModel):
    """Restorable rules-only plan for a user-selected saved research paper."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reproduction-pipeline.v1"] = "reproduction-pipeline.v1"
    pipeline_id: str
    conversation_id: str
    source_bundle_id: str
    selected_paper: ReproductionSelectedPaper
    reproduction_goal: ReproductionPipelineItem
    research_question: ReproductionPipelineItem
    known_method: ReproductionPipelineItem
    data_and_sample_conditions: list[ReproductionPipelineItem]
    candidate_baselines: list[ReproductionPipelineItem]
    metrics: list[ReproductionPipelineItem]
    experiment_steps: list[ReproductionPipelineItem]
    resources: list[ReproductionPipelineItem]
    risks: list[ReproductionPipelineItem]
    ethics: list[ReproductionPipelineItem]
    acceptance_criteria: list[ReproductionPipelineItem] = Field(default_factory=list, max_length=12)
    confirmation_items: list[ReproductionPipelineItem]
    tasks: list[ReproductionTask]
    two_week_mvp: list[ReproductionPipelineItem]
    created_at: datetime
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)
    paper_reading: PaperReadingEvidence | None = None


class CreateReproductionPipelineRequest(BaseModel):
    """Explicit selection of a paper already saved in this conversation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_bundle_id: str = Field(min_length=1, max_length=64)
    paper_url: str = Field(min_length=1, max_length=2000)
    paper_pdf_url: str | None = Field(default=None, max_length=2000)


class PaperBlueprintReference(BaseModel):
    """A traceable reference to an already stored local research artefact."""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal[
        "research_profile",
        "research_plan",
        "academic_evidence",
        "experiment_evidence",
    ]
    bundle_id: str | None = None
    label: str = Field(min_length=1, max_length=1000)
    classification: AnalysisClassification
    source_url: str | None = Field(default=None, max_length=2000)
    information_scope: str = Field(min_length=1, max_length=200)


class PaperBlueprintEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=2000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1000)


class PaperBlueprintSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Literal["摘要", "介绍", "文献综述", "方法", "实验"]
    writing_goal: PaperBlueprintEntry
    evidence_references: list[PaperBlueprintReference] = Field(default_factory=list, max_length=24)
    missing_evidence: list[PaperBlueprintEntry] = Field(default_factory=list, max_length=12)
    forbidden_claims: list[str] = Field(default_factory=list, max_length=12)
    citation_placeholders: list[PaperBlueprintReference] = Field(
        default_factory=list, max_length=24
    )


_EXPECTED_BLUEPRINT_SECTIONS = ("摘要", "介绍", "文献综述", "方法", "实验")


class PaperBlueprint(BaseModel):
    """A rule-governed writing outline, never a claim that a paper is ready to submit."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["paper-blueprint.v2"] = "paper-blueprint.v2"
    conversation_id: str
    candidate_titles: list[PaperBlueprintEntry] = Field(min_length=1, max_length=3)
    target_submission_direction: PaperBlueprintEntry
    abstract_requirements: list[PaperBlueprintEntry] = Field(min_length=4, max_length=8)
    sections: list[PaperBlueprintSection] = Field(min_length=5, max_length=5)
    submission_readiness: PaperBlueprintEntry
    gaps: list[PaperBlueprintEntry] = Field(min_length=1, max_length=12)
    provenance_note: str = Field(min_length=1, max_length=1000)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)

    @field_validator("sections")
    @classmethod
    def _validate_sections_order_and_abstract_length(
        cls, sections: list[PaperBlueprintSection]
    ) -> list[PaperBlueprintSection]:
        if len(sections) != 5:
            raise ValueError(f"sections 必须包含恰好 5 个段落，实际包含 {len(sections)} 个")
        actual_order = tuple(s.section for s in sections)
        if actual_order != _EXPECTED_BLUEPRINT_SECTIONS:
            raise ValueError(
                f"sections 必须严格按 {_EXPECTED_BLUEPRINT_SECTIONS} 顺序排列，"
                f"实际顺序为 {actual_order}"
            )
        abstract_section = sections[0]
        if len(abstract_section.writing_goal.content) > 200:
            raise ValueError(
                "摘要段 writing_goal（结构化摘要骨架）长度不得超过 200 字，"
                f"实际为 {len(abstract_section.writing_goal.content)} 字"
            )
        return sections


class PaperSection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    section_id: str
    heading: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=20000)
    order: int = Field(ge=1, le=100)


class CreatePaperDraftRequest(BaseModel):
    """A user-pasted local draft; file import is intentionally not supported."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=60000)
    format: Literal["markdown", "plain_text"]

    @field_validator("content")
    @classmethod
    def reject_secrets_and_local_paths(cls, value: str) -> str:
        lowered = value.casefold()
        if any(marker in lowered for marker in ("api_key=", "api_key =", "sk-")):
            raise ValueError("draft content must not include API keys")
        if re.search(r"[a-z]:\\(?:users|home|private)\\", lowered):
            raise ValueError("draft content must not include a local private path")
        return value


class PaperDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["paper-draft.v1"] = "paper-draft.v1"
    draft_id: str
    conversation_id: str
    title: str
    content: str
    format: Literal["markdown", "plain_text"]
    version: int = Field(ge=1)
    sections: list[PaperSection] = Field(default_factory=list, max_length=100)
    created_at: datetime
    source_scope: Literal["user_pasted_local_session"] = "user_pasted_local_session"


ReviewSeverity = Literal["blocker", "major", "minor", "suggestion"]
ReviewSourceScope = Literal[
    "draft_text",
    "research_profile",
    "research_plan",
    "academic_metadata_abstract",
    "experiment_evidence",
]


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    severity: ReviewSeverity
    section: str = Field(min_length=1, max_length=300)
    issue: str = Field(min_length=1, max_length=1500)
    why_it_matters: str = Field(min_length=1, max_length=2000)
    recommended_action: str = Field(min_length=1, max_length=2000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1500)
    source_scope: ReviewSourceScope
    related_blueprint_item: str | None = Field(default=None, max_length=500)
    can_auto_suggest: bool = False


class RevisionTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    finding_id: str
    status: Literal["pending", "accepted", "skipped", "completed"] = "pending"
    finding: ReviewFinding
    created_at: datetime
    updated_at: datetime


class PaperReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["paper-review.v1"] = "paper-review.v1"
    review_id: str
    draft_id: str
    conversation_id: str
    findings: list[ReviewFinding] = Field(min_length=1, max_length=40)
    revision_tasks: list[RevisionTask] = Field(min_length=1, max_length=40)
    provenance_note: str = Field(min_length=1, max_length=1500)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    event_count: int = Field(default=0, ge=0)
    created_at: datetime


class UpdateRevisionTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "skipped"]


class RevisionSuggestion(BaseModel):
    """One user-confirmable paragraph-level suggestion; it never alters a draft by itself."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["revision-suggestion.v1"] = "revision-suggestion.v1"
    suggestion_id: str
    revision_task_id: str
    draft_id: str
    section_heading: str = Field(min_length=1, max_length=300)
    paragraph_anchor: str = Field(min_length=1, max_length=300)
    original_excerpt: str = Field(min_length=1, max_length=8000)
    candidate_text: str = Field(min_length=1, max_length=8000)
    rationale: str = Field(min_length=1, max_length=2000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1500)
    source_scope: ReviewSourceScope
    to_verify_items: list[str] = Field(default_factory=list, max_length=12)
    generation_mode: Literal["llm", "rules", "rules_fallback"] = "rules"
    run_id: str | None = None
    created_at: datetime


class ApplyRevisionSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["accepted", "skipped"]
    candidate_text: str | None = Field(default=None, min_length=1, max_length=8000)


class PaperRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["paper-revision.v1"] = "paper-revision.v1"
    revision_id: str
    parent_draft_id: str
    parent_revision_id: str | None = None
    review_id: str
    version: int = Field(ge=2)
    content: str
    applied_task_ids: list[str] = Field(min_length=1, max_length=40)
    applied_suggestion_ids: list[str] = Field(default_factory=list, max_length=40)
    change_summary: list[str] = Field(min_length=1, max_length=40)
    diff_preview: str = Field(min_length=1, max_length=30000)
    created_at: datetime
    source_scope: Literal["user_pasted_draft_plus_accepted_suggestions"] = (
        "user_pasted_draft_plus_accepted_suggestions"
    )


CitationTargetDocument = Literal["paper_draft", "paper_revision", "paper_blueprint"]
SelectedCitationStatus = Literal["selected", "inserted", "skipped"]


class CitationCandidate(BaseModel):
    """A deterministic, local view of one paper in a saved evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["citation-candidate.v1"] = "citation-candidate.v1"
    citation_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    evidence_bundle_id: str = Field(min_length=1, max_length=100)
    paper_title: str = Field(min_length=1, max_length=1000)
    authors: list[str] = Field(default_factory=list, max_length=32)
    year: int | None = None
    source_name: str | None = Field(default=None, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    doi: str | None = Field(default=None, max_length=300)
    arxiv_id: str | None = Field(default=None, max_length=300)
    abstract_scope: Literal["metadata_only", "metadata_and_abstract"]
    metadata_completeness: Literal["complete", "partial"]
    classification: AnalysisClassification
    source_scope: Literal["metadata_and_abstract_only"] = "metadata_and_abstract_only"
    created_at: datetime


class ReferenceEntryDraft(BaseModel):
    """A human-readable draft, explicitly not a publication-style citation."""

    model_config = ConfigDict(extra="forbid")

    reference_id: str = Field(min_length=1, max_length=100)
    selected_citation_id: str = Field(min_length=1, max_length=100)
    display_text: str = Field(min_length=1, max_length=3000)
    citation_key: str = Field(min_length=1, max_length=160)
    metadata_fields: dict[str, str | int | None]
    classification: AnalysisClassification
    to_verify_items: list[str] = Field(default_factory=list, max_length=12)
    source_scope: Literal["metadata_and_abstract_only"] = "metadata_and_abstract_only"


class CreateSelectedCitationRequest(BaseModel):
    """An explicit user choice of a saved source and a suggested local position."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_bundle_id: str = Field(min_length=1, max_length=100)
    paper_url: str = Field(min_length=1, max_length=2000)
    target_document: CitationTargetDocument
    target_section: str = Field(min_length=1, max_length=300)
    paragraph_anchor: str = Field(min_length=1, max_length=300)
    user_note: str | None = Field(default=None, max_length=1000)


class UpdateSelectedCitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["inserted", "skipped"]


class SelectedCitation(BaseModel):
    """A persisted selection. It never mutates the draft or revision text."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["selected-citation.v1"] = "selected-citation.v1"
    selected_citation_id: str
    session_id: str
    citation: CitationCandidate
    target_document: CitationTargetDocument
    target_section: str
    paragraph_anchor: str
    citation_placeholder: str
    user_note: str | None = None
    status: SelectedCitationStatus = "selected"
    reference_entry: ReferenceEntryDraft
    created_at: datetime


CitationQualityStatus = Literal["empty", "needs_review", "review_ready"]
CitationCoverageStatus = Literal["mapped", "needs_verification"]


class CitationQualityIssue(BaseModel):
    """One local citation gap with an explicit source and fact boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    issue_code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1500)
    selected_citation_ids: list[str] = Field(default_factory=list, max_length=40)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1500)


class CitationCoverageItem(BaseModel):
    """A user-created source-to-section mapping, not proof that a claim is supported."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_document: CitationTargetDocument
    target_section: str = Field(min_length=1, max_length=300)
    selected_citation_ids: list[str] = Field(min_length=1, max_length=40)
    source_titles: list[str] = Field(min_length=1, max_length=40)
    citation_placeholders: list[str] = Field(min_length=1, max_length=40)
    status: CitationCoverageStatus
    classification: Literal["inference"] = "inference"
    information_scopes: list[Literal["metadata_only", "metadata_and_abstract"]] = Field(
        min_length=1, max_length=2
    )
    basis: str = Field(min_length=1, max_length=1500)
    to_verify_items: list[str] = Field(default_factory=list, max_length=40)


class CitationQualityCheck(BaseModel):
    """A persisted rules-only check over citations explicitly selected by one user."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["citation-quality-check.v1"] = "citation-quality-check.v1"
    check_id: str = Field(min_length=1, max_length=100)
    session_id: str = Field(min_length=1, max_length=100)
    checked_at: datetime
    quality_status: CitationQualityStatus
    selected_source_count: int = Field(ge=0, le=1000)
    unique_source_count: int = Field(ge=0, le=1000)
    mapped_section_count: int = Field(ge=0, le=100)
    core_section_coverage_percent: int = Field(ge=0, le=100)
    coverage_items: list[CitationCoverageItem] = Field(default_factory=list, max_length=100)
    unmapped_core_sections: list[str] = Field(default_factory=list, max_length=20)
    uninserted_placeholders: list[CitationQualityIssue] = Field(
        default_factory=list, max_length=100
    )
    duplicate_selections: list[CitationQualityIssue] = Field(default_factory=list, max_length=100)
    metadata_gaps: list[CitationQualityIssue] = Field(default_factory=list, max_length=100)
    author_verification_items: list[CitationQualityIssue] = Field(
        default_factory=list, max_length=100
    )
    empty_state_message: str | None = Field(default=None, max_length=1000)
    boundary_note: str = Field(min_length=1, max_length=1500)
    source_scope: Literal["local_selected_evidence_only"] = "local_selected_evidence_only"


class ReferenceDraftItem(BaseModel):
    """One traceable, non-publication-style reference line."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    selected_citation_id: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=2000)
    citation_placeholder: str = Field(min_length=1, max_length=1000)
    display_text: str = Field(min_length=1, max_length=3000)
    classification: AnalysisClassification
    to_verify_items: list[str] = Field(default_factory=list, max_length=12)
    format_notice: str = Field(min_length=1, max_length=300)


class ReferenceDraftVerificationItem(BaseModel):
    """Missing saved metadata that an author or advisor must verify."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    selected_citation_id: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=2000)
    missing_fields: list[str] = Field(min_length=1, max_length=12)
    classification: Literal["to_verify"] = "to_verify"
    basis: str = Field(min_length=1, max_length=1000)


class ReferenceDraftPackage(BaseModel):
    """A stable copy surface derived only from active local selections."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reference-draft-package.v1"] = "reference-draft-package.v1"
    session_id: str = Field(min_length=1, max_length=100)
    entries: list[ReferenceDraftItem] = Field(default_factory=list, max_length=1000)
    copy_text: str = Field(default="", max_length=500_000)
    verification_items: list[ReferenceDraftVerificationItem] = Field(
        default_factory=list, max_length=1000
    )
    empty_state_message: str | None = Field(default=None, max_length=1000)
    boundary_note: str = Field(min_length=1, max_length=1500)
    source_scope: Literal["local_selected_evidence_only"] = "local_selected_evidence_only"


class SubmissionProfileInput(BaseModel):
    """User-known submission constraints; no venue rule is fetched or inferred."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_venue: str | None = Field(default=None, min_length=1, max_length=300)
    anonymity_required: bool | None = None
    length_or_section_requirements: str | None = Field(default=None, min_length=1, max_length=1000)
    ethics_and_data_requirements: str | None = Field(default=None, min_length=1, max_length=1000)
    user_notes: str | None = Field(default=None, min_length=1, max_length=1500)

    @field_validator(
        "target_venue",
        "length_or_section_requirements",
        "ethics_and_data_requirements",
        "user_notes",
    )
    @classmethod
    def reject_secrets_and_private_paths(cls, value: str | None) -> str | None:
        """Keep local submission metadata free of credentials and personal file paths."""
        if value is None:
            return value
        lowered = value.lower()
        if "api_key=" in lowered or "api_key =" in lowered or "sk-" in lowered:
            raise ValueError("Submission profile fields must not contain API keys or tokens.")
        if re.search(r"(?i)[a-z]:\\(?:users|home|private)\\", value):
            raise ValueError("Submission profile fields must not contain private local paths.")
        return value


class SubmissionProfile(SubmissionProfileInput):
    """Persisted local submission-profile data controlled by the user."""

    schema_version: Literal["submission-profile.v1"] = "submission-profile.v1"
    profile_id: str
    conversation_id: str
    created_at: datetime
    updated_at: datetime


SubmissionReadinessStatus = Literal["not_ready", "needs_review", "checklist_complete"]
SubmissionSourceScope = Literal[
    "draft_text",
    "revision_preview",
    "paper_review",
    "experiment_evidence",
    "academic_metadata_abstract",
    "submission_profile",
    "manual_confirmation",
]


class SubmissionReadinessItem(BaseModel):
    """One rules-based check; it is never a publication or acceptance verdict."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    category: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1500)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1500)
    source_scope: SubmissionSourceScope


class SubmissionReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["submission-readiness.v1"] = "submission-readiness.v1"
    check_id: str
    draft_id: str
    revision_id: str | None = None
    conversation_id: str
    submission_profile: SubmissionProfile | None = None
    readiness_status: SubmissionReadinessStatus
    blockers: list[SubmissionReadinessItem] = Field(default_factory=list, max_length=40)
    warnings: list[SubmissionReadinessItem] = Field(default_factory=list, max_length=40)
    manual_checks: list[SubmissionReadinessItem] = Field(default_factory=list, max_length=40)
    fact_boundary_notes: list[SubmissionReadinessItem] = Field(default_factory=list, max_length=20)
    recommended_next_actions: list[SubmissionReadinessItem] = Field(
        default_factory=list, max_length=20
    )
    created_at: datetime
    source_scope: Literal["local_saved_research_artifacts"] = "local_saved_research_artifacts"


class PaperExportFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,120}$")
    content_type: Literal["text/markdown", "application/json"]
    content: str = Field(min_length=1, max_length=180000)


class PaperExportPackage(BaseModel):
    """Text returned only after an explicit export request; the server never writes files."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["paper-export.v1"] = "paper-export.v1"
    draft_id: str
    revision_id: str
    readiness_check_id: str
    files: list[PaperExportFile] = Field(min_length=2, max_length=2)
    provenance_note: str = Field(min_length=1, max_length=1000)
