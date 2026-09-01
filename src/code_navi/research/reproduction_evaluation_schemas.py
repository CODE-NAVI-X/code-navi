"""Public contracts for evidence-bounded paper reproduction evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .conversation_schemas import AnalysisClassification, DatasetRef, MetricSpec

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
    dataset_refs: list[DatasetRef] = Field(default_factory=list)
    baseline_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    metric_entries: list[ReproductionPipelineEvidenceEntry] = Field(default_factory=list)
    metric_specs: list[MetricSpec] = Field(default_factory=list)
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


class ReproductionEvaluationCriterion(BaseModel):
    """One conservative 0/1/2 criterion out of the fixed six."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    criterion_no: int = Field(ge=1, le=6)
    title: str = Field(min_length=1, max_length=100)
    score: Literal[0, 1, 2]
    basis: str = Field(min_length=1, max_length=500)
    evidence_refs: list[ReproductionEvaluationEvidence] | None = None
    improvement_task_id: str | None = None


class ReproductionEvaluationScoreSummaryV2(BaseModel):
    """v2 score summary based on 6 criteria and 12-point maximum."""

    model_config = ConfigDict(extra="forbid")

    earned_score: int = Field(ge=0, le=12)
    scored_maximum: int = Field(ge=0, le=12)
    total_maximum: Literal[12] = 12
    scored_criterion_count: int = Field(ge=0, le=6)
    unscored_criterion_count: int = Field(ge=0, le=6)
    display: str = Field(min_length=1, max_length=200)


_V2_CRITERION_TITLES = {
    1: "研究问题与假设可复述性",
    2: "方法可执行性（步骤完整、变量可操作）",
    3: "数据可得性（公开链接与许可）",
    4: "指标与统计方法正确性（对照标准目录）",
    5: "计算资源与时间可行性",
    6: "结果核验路径（baseline 与预期区间）",
}


class ReproductionProjectEvaluationV2(BaseModel):
    """v2 conservative evaluation snapshot locking exactly 6 criteria with 12-point scale."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["reproduction-project-evaluation.v2"] = (
        "reproduction-project-evaluation.v2"
    )
    evaluation_id: str
    conversation_id: str
    pipeline_id: str | None = None
    pipeline_contract_status: Literal["available", "unavailable"]
    selected_paper_count: int = Field(ge=0)
    experiment_record_count: int = Field(ge=0)
    total_score: int = Field(ge=0, le=12)
    score_summary: ReproductionEvaluationScoreSummaryV2
    criteria: list[ReproductionEvaluationCriterion] = Field(min_length=6, max_length=6)
    improvement_tasks: list[ReproductionImprovementTask] = Field(default_factory=list)
    created_at: datetime
    boundary_note: str = Field(min_length=1, max_length=1600)

    @model_validator(mode="after")
    def validate_criteria_and_total(self) -> ReproductionProjectEvaluationV2:
        nos = [c.criterion_no for c in self.criteria]
        if nos != [1, 2, 3, 4, 5, 6]:
            raise ValueError(f"v2 criteria must have criterion_no 1 through 6, got {nos}")
        for c in self.criteria:
            expected_title = _V2_CRITERION_TITLES[c.criterion_no]
            if c.title != expected_title:
                raise ValueError(
                    f"Criterion {c.criterion_no} title must be '{expected_title}', got '{c.title}'"
                )
        sum_score = sum(c.score for c in self.criteria)
        if self.total_score != sum_score:
            raise ValueError(
                f"total_score ({self.total_score}) must equal sum of criteria scores ({sum_score})"
            )
        return self


class ReproductionEvaluationListItemResponse(BaseModel):
    """Item for evaluation list endpoint with schema_version for proper frontend rendering."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "reproduction-project-evaluation.v1", "reproduction-project-evaluation.v2"
    ]
    evaluation_id: str
    conversation_id: str
    pipeline_id: str | None = None
    pipeline_contract_status: Literal["available", "unavailable"]
    selected_paper_count: int = Field(ge=0)
    experiment_record_count: int = Field(ge=0)
    total_score: int = Field(ge=0, le=100)
    display_score: str = Field(min_length=1, max_length=200)
    created_at: datetime


class ReproductionProjectEvaluation(BaseModel):
    """Persisted five-dimensional snapshot (v1); it is not a quality or publication verdict."""

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


ReproductionProjectEvaluationV1 = ReproductionProjectEvaluation
ReproductionProjectEvaluationDetail = (
    ReproductionProjectEvaluation | ReproductionProjectEvaluationV2
)
