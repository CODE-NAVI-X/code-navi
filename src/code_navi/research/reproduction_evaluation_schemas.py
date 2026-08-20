"""Public contracts for evidence-bounded paper reproduction evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .conversation_schemas import AnalysisClassification

ReproductionEvaluationDimension = Literal[
    "research_definition",
    "source_traceability",
    "reproduction_plan",
    "execution_evidence",
    "reflection_and_compliance",
]
ReproductionEvaluationStatus = Literal[
    "not_evaluable",
    "needs_revision",
    "evidence_partial",
    "checklist_complete",
]
ReproductionImprovementTaskStatus = Literal[
    "pending",
    "accepted",
    "skipped",
    "completed",
]


class CreateReproductionEvaluationRequest(BaseModel):
    """Explicit user confirmation for one offline evaluation snapshot."""

    model_config = ConfigDict(extra="forbid")

    user_confirmed: Literal[True]


class ReproductionPipelineEvidenceEntry(BaseModel):
    """One bounded entry exposed by A's Pipeline through a read-only adapter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=2000)
    classification: AnalysisClassification
    basis: str = Field(min_length=1, max_length=1000)
    source_scope: str = Field(min_length=1, max_length=200)


class ReproductionPipelineEvaluationView(BaseModel):
    """B-owned adapter view; it does not redefine or persist A's Pipeline model."""

    model_config = ConfigDict(extra="forbid")

    pipeline_id: str = Field(min_length=1, max_length=100)
    target_paper_title: str = Field(min_length=1, max_length=1000)
    target_paper_url: str | None = Field(default=None, max_length=2000)
    objective_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    dataset_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    baseline_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    metric_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    step_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    resource_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    risk_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    ethics_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)


class ReproductionEvaluationEvidence(BaseModel):
    """Traceable basis used by one dimension without broadening its information scope."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: Literal[
        "research_profile",
        "selected_citation",
        "reproduction_pipeline",
        "experiment_evidence",
    ]
    source_id: str | None = Field(default=None, max_length=100)
    label: str = Field(min_length=1, max_length=1000)
    classification: AnalysisClassification
    information_scope: str = Field(min_length=1, max_length=300)
    basis: str = Field(min_length=1, max_length=1000)


class ReproductionEvaluationDimensionResult(BaseModel):
    """One 20-point dimension; missing evidence remains genuinely unscored."""

    model_config = ConfigDict(extra="forbid")

    dimension: ReproductionEvaluationDimension
    label: str = Field(min_length=1, max_length=100)
    status: ReproductionEvaluationStatus
    score: int | None = Field(default=None, ge=0, le=20)
    maximum_score: Literal[20] = 20
    issues: list[str] = Field(default_factory=list, max_length=12)
    evidence: list[ReproductionEvaluationEvidence] = Field(default_factory=list, max_length=30)
    fact_boundary: str = Field(min_length=1, max_length=1200)
    to_verify: list[str] = Field(default_factory=list, max_length=12)
    next_suggestions: list[str] = Field(default_factory=list, max_length=8)


class ReproductionEvaluationScoreSummary(BaseModel):
    """Separate earned, currently scorable, and structural maxima."""

    model_config = ConfigDict(extra="forbid")

    earned_score: int = Field(ge=0, le=100)
    scored_maximum: int = Field(ge=0, le=100)
    total_maximum: Literal[100] = 100
    scored_dimension_count: int = Field(ge=0, le=5)
    unscored_dimension_count: int = Field(ge=0, le=5)
    display: str = Field(min_length=1, max_length=200)


class ReproductionImprovementTask(BaseModel):
    """A persisted suggestion whose state changes only after an explicit user action."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reproduction-improvement-task.v1"] = (
        "reproduction-improvement-task.v1"
    )
    task_id: str
    evaluation_id: str
    conversation_id: str
    dimension: ReproductionEvaluationDimension
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=1200)
    status: ReproductionImprovementTaskStatus = "pending"
    classification: Literal["to_verify"] = "to_verify"
    basis: str = Field(min_length=1, max_length=1000)
    created_at: datetime
    updated_at: datetime


class UpdateReproductionImprovementTaskRequest(BaseModel):
    """User-controlled task transition; completed work is never inferred."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "skipped", "completed"]


class ReproductionProjectEvaluation(BaseModel):
    """Persisted five-dimensional snapshot; it is not a quality or publication verdict."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reproduction-project-evaluation.v1"] = (
        "reproduction-project-evaluation.v1"
    )
    evaluation_id: str
    conversation_id: str
    pipeline_id: str | None = None
    pipeline_contract_status: Literal["available", "unavailable"]
    selected_paper_count: int = Field(ge=0)
    experiment_record_count: int = Field(ge=0)
    score_summary: ReproductionEvaluationScoreSummary
    dimensions: list[ReproductionEvaluationDimensionResult] = Field(
        min_length=5, max_length=5
    )
    improvement_tasks: list[ReproductionImprovementTask] = Field(default_factory=list)
    created_at: datetime
    boundary_note: str = Field(min_length=1, max_length=1600)
