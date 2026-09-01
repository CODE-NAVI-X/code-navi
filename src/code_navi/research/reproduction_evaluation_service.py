"""Persistence and orchestration for user-triggered reproduction evaluations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from .conversation_schemas import (
    DatasetRef,
    ExperimentDesign,
    ExperimentEvidenceBundle,
    MetricSpec,
    ReproductionPipeline,
    ReproductionPipelineItem,
    ResearchPlanEntry,
    ResearchProfile,
    SelectedCitation,
)
from .conversation_service import ConversationNotFoundError
from .models import (
    ResearchConversationModel,
    ResearchExperimentEvidenceBundleModel,
    ResearchReproductionEvaluationModel,
    ResearchReproductionImprovementTaskModel,
    ResearchReproductionPipelineModel,
    ResearchSelectedCitationModel,
)
from .reproduction_evaluation import evaluate_reproduction_project_v2
from .reproduction_evaluation_schemas import (
    ReproductionEvaluationDimensionResult,
    ReproductionEvaluationScoreSummaryV2,
    ReproductionImprovementTask,
    ReproductionPipelineEvaluationView,
    ReproductionPipelineEvidenceEntry,
    ReproductionProjectEvaluationDetail,
    ReproductionProjectEvaluationV1,
    ReproductionProjectEvaluationV2,
    UpdateReproductionImprovementTaskRequest,
)


class ReproductionEvaluationNotFoundError(LookupError):
    """Raised when a saved evaluation does not exist."""


class ReproductionImprovementTaskNotFoundError(LookupError):
    """Raised when a saved evaluation task does not exist."""


class InvalidReproductionTaskTransitionError(ValueError):
    """Raised when a user attempts an invalid task-state transition."""


class ReproductionPipelineReader(Protocol):
    """Read-only adapter boundary owned by B, implemented against A's stable contract."""

    def load(
        self,
        conversation_id: str,
        db: Session,
    ) -> ReproductionPipelineEvaluationView | None: ...


class StoredReproductionPipelineReader:
    """Adapt A's latest persisted Pipeline and PR-B's ExperimentDesign into B's evaluation view."""

    def load(
        self,
        conversation_id: str,
        db: Session,
    ) -> ReproductionPipelineEvaluationView | None:
        pipeline_record = (
            db.query(ResearchReproductionPipelineModel)
            .filter(ResearchReproductionPipelineModel.conversation_id == conversation_id)
            .order_by(ResearchReproductionPipelineModel.created_at.desc())
            .first()
        )

        conversation = db.get(ResearchConversationModel, conversation_id)
        dataset_refs: list[DatasetRef] = []
        metric_specs: list[MetricSpec] = []
        exp_design: ExperimentDesign | None = None
        if conversation is not None and conversation.generated_artifacts:
            exp_data = conversation.generated_artifacts.get("experiment_design")
            if exp_data:
                try:
                    exp_design = ExperimentDesign.model_validate(exp_data)
                    dataset_refs = list(exp_design.dataset_refs)
                    metric_specs = list(exp_design.metric_specs)
                except Exception:
                    pass

        if pipeline_record is None and exp_design is None:
            return None

        if pipeline_record is not None:
            pipeline = ReproductionPipeline.model_validate(pipeline_record.pipeline_data)
            return ReproductionPipelineEvaluationView(
                pipeline_id=pipeline.pipeline_id,
                target_paper_title=pipeline.selected_paper.title,
                target_paper_url=pipeline.selected_paper.url,
                objective_entries=[
                    self._entry(pipeline.reproduction_goal),
                    self._entry(pipeline.research_question),
                ],
                dataset_entries=self._entries(pipeline.data_and_sample_conditions),
                dataset_refs=dataset_refs,
                baseline_entries=self._entries(pipeline.candidate_baselines),
                metric_entries=self._entries(pipeline.metrics),
                metric_specs=metric_specs,
                step_entries=self._entries(pipeline.experiment_steps),
                resource_entries=self._entries(pipeline.resources),
                risk_entries=self._entries(pipeline.risks),
                ethics_entries=self._entries(pipeline.ethics),
            )

        assert exp_design is not None
        return ReproductionPipelineEvaluationView(
            pipeline_id=f"exp-design-{conversation_id}",
            target_paper_title="实验设计方案",
            target_paper_url="",
            objective_entries=[self._entry_from_plan(exp_design.hypothesis)],
            dataset_entries=[self._entry_from_plan(d) for d in exp_design.data_sources],
            dataset_refs=dataset_refs,
            baseline_entries=[self._entry_from_plan(b) for b in exp_design.baselines],
            metric_entries=[self._entry_from_plan(m) for m in exp_design.metrics],
            metric_specs=metric_specs,
            step_entries=[self._entry_from_plan(s) for s in exp_design.steps],
            resource_entries=[self._entry_from_plan(r) for r in exp_design.resources],
            risk_entries=[self._entry_from_plan(rk) for rk in exp_design.risks],
            ethics_entries=[],
        )

    @staticmethod
    def _entry(item: ReproductionPipelineItem) -> ReproductionPipelineEvidenceEntry:
        return ReproductionPipelineEvidenceEntry.model_validate(item.model_dump())

    @staticmethod
    def _entry_from_plan(item: ResearchPlanEntry) -> ReproductionPipelineEvidenceEntry:
        return ReproductionPipelineEvidenceEntry(
            content=item.content,
            classification=item.classification,
            basis=item.basis,
            source_scope="experiment_design",
        )

    @classmethod
    def _entries(
        cls,
        items: list[ReproductionPipelineItem],
    ) -> list[ReproductionPipelineEvidenceEntry]:
        return [cls._entry(item) for item in items]


class ReproductionEvaluationService:
    """Build and restore offline evaluations without executing or retrieving anything."""

    def __init__(self, pipeline_reader: ReproductionPipelineReader | None = None) -> None:
        self.pipeline_reader = pipeline_reader or StoredReproductionPipelineReader()

    def create(
        self,
        conversation_id: str,
        db: Session,
    ) -> ReproductionProjectEvaluationDetail:
        """Persist one immutable evaluation snapshot after an explicit user action."""
        conversation = db.get(ResearchConversationModel, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        profile = ResearchProfile.model_validate(conversation.profile_data)
        citations = self._selected_citations(conversation_id, db)
        experiment_bundles = self._experiment_bundles(conversation_id, db)
        pipeline = self.pipeline_reader.load(conversation_id, db)
        created_at = datetime.now(UTC)
        evaluation_id = str(uuid.uuid4())
        criteria, total_score, tasks = evaluate_reproduction_project_v2(
            profile,
            citations,
            experiment_bundles,
            pipeline,
            conversation_id=conversation_id,
            evaluation_id=evaluation_id,
            created_at=created_at,
        )
        evaluation = ReproductionProjectEvaluationV2(
            evaluation_id=evaluation_id,
            conversation_id=conversation_id,
            pipeline_id=pipeline.pipeline_id if pipeline else None,
            pipeline_contract_status="available" if pipeline else "unavailable",
            selected_paper_count=len(
                {
                    item.citation.url.casefold()
                    for item in citations
                    if item.status != "skipped"
                }
            ),
            experiment_record_count=len(experiment_bundles),
            total_score=total_score,
            score_summary=ReproductionEvaluationScoreSummaryV2(
                earned_score=total_score,
                scored_maximum=12,
                total_maximum=12,
                scored_criterion_count=len(criteria),
                unscored_criterion_count=0,
                display=f"{total_score}/12（共 6 项准则，满分 12 分）",
            ),
            criteria=criteria,
            improvement_tasks=tasks,
            created_at=created_at,
            boundary_note=(
                "本评估只读取当前会话已保存的科研画像、用户明确选择的来源、"
                "可用的 ReproductionPipeline 只读视图和用户提交的实验文本。"
                "它不联网、不读取论文全文、不运行代码、不改写草稿；分数只表示记录与证据"
                "完整度，不表示复现成功、论文质量、可投稿或会被接收。"
            ),
        )
        db.add(
            ResearchReproductionEvaluationModel(
                id=evaluation_id,
                conversation_id=conversation_id,
                evaluation_data=evaluation.model_dump(
                    mode="json", exclude={"improvement_tasks"}
                ),
                created_at=created_at,
            )
        )
        db.add_all(
            [
                ResearchReproductionImprovementTaskModel(
                    id=task.task_id,
                    evaluation_id=evaluation_id,
                    conversation_id=conversation_id,
                    task_data=task.model_dump(mode="json"),
                    created_at=created_at,
                    updated_at=created_at,
                )
                for task in tasks
            ]
        )
        db.commit()
        return evaluation

    def list(
        self,
        conversation_id: str,
        db: Session,
    ) -> list[ReproductionProjectEvaluationDetail]:
        """Restore saved snapshots and current task states without re-running evaluation."""
        if db.get(ResearchConversationModel, conversation_id) is None:
            raise ConversationNotFoundError(conversation_id)
        records = (
            db.query(ResearchReproductionEvaluationModel)
            .filter(ResearchReproductionEvaluationModel.conversation_id == conversation_id)
            .order_by(ResearchReproductionEvaluationModel.created_at.desc())
            .all()
        )
        return [self._restore(record, db) for record in records]

    def get(
        self,
        evaluation_id: str,
        db: Session,
    ) -> ReproductionProjectEvaluationDetail:
        record = db.get(ResearchReproductionEvaluationModel, evaluation_id)
        if record is None:
            raise ReproductionEvaluationNotFoundError(evaluation_id)
        return self._restore(record, db)

    def update_task(
        self,
        task_id: str,
        request: UpdateReproductionImprovementTaskRequest,
        db: Session,
    ) -> ReproductionImprovementTask:
        """Apply only an explicit, valid user-controlled task transition."""
        record = db.get(ResearchReproductionImprovementTaskModel, task_id)
        if record is None:
            raise ReproductionImprovementTaskNotFoundError(task_id)
        task = ReproductionImprovementTask.model_validate(record.task_data)
        allowed = {
            "pending": {"accepted", "skipped"},
            "accepted": {"completed", "skipped"},
            "skipped": set(),
            "completed": set(),
        }
        if request.status != task.status and request.status not in allowed[task.status]:
            raise InvalidReproductionTaskTransitionError(
                f"Cannot change reproduction improvement task from {task.status} "
                f"to {request.status}."
            )
        updated = task.model_copy(
            update={"status": request.status, "updated_at": datetime.now(UTC)}
        )
        record.task_data = updated.model_dump(mode="json")
        record.updated_at = updated.updated_at
        db.commit()
        return updated

    def _restore(
        self,
        record: ResearchReproductionEvaluationModel,
        db: Session,
    ) -> ReproductionProjectEvaluationDetail:
        tasks = (
            db.query(ResearchReproductionImprovementTaskModel)
            .filter(
                ResearchReproductionImprovementTaskModel.evaluation_id == record.id
            )
            .order_by(ResearchReproductionImprovementTaskModel.created_at.asc())
            .all()
        )
        schema_version = record.evaluation_data.get("schema_version")
        if schema_version == "reproduction-project-evaluation.v1":
            return ReproductionProjectEvaluationV1.model_validate(
                {
                    **record.evaluation_data,
                    "improvement_tasks": [task.task_data for task in tasks],
                }
            )
        return ReproductionProjectEvaluationV2.model_validate(
            {
                **record.evaluation_data,
                "improvement_tasks": [task.task_data for task in tasks],
            }
        )

    @staticmethod
    def _selected_citations(
        conversation_id: str,
        db: Session,
    ) -> list[SelectedCitation]:
        records = (
            db.query(ResearchSelectedCitationModel)
            .filter(ResearchSelectedCitationModel.conversation_id == conversation_id)
            .order_by(ResearchSelectedCitationModel.created_at.asc())
            .all()
        )
        return [SelectedCitation.model_validate(record.selection_data) for record in records]

    @staticmethod
    def _experiment_bundles(
        conversation_id: str,
        db: Session,
    ) -> list[ExperimentEvidenceBundle]:
        records = (
            db.query(ResearchExperimentEvidenceBundleModel)
            .filter(
                ResearchExperimentEvidenceBundleModel.conversation_id == conversation_id
            )
            .order_by(ResearchExperimentEvidenceBundleModel.created_at.asc())
            .all()
        )
        return [ExperimentEvidenceBundle.model_validate(record.bundle_data) for record in records]

    @staticmethod
    def _build_tasks(
        evaluation_id: str,
        conversation_id: str,
        dimensions: list[ReproductionEvaluationDimensionResult],
        created_at: datetime,
    ) -> list[ReproductionImprovementTask]:
        tasks: list[ReproductionImprovementTask] = []
        for dimension in dimensions:
            for suggestion in dimension.next_suggestions[:3]:
                tasks.append(
                    ReproductionImprovementTask(
                        task_id=str(uuid.uuid4()),
                        evaluation_id=evaluation_id,
                        conversation_id=conversation_id,
                        dimension=dimension.dimension,
                        title=f"改进“{dimension.label}”",
                        description=suggestion,
                        basis=(
                            "由当前评估维度的显式证据缺口生成；完成状态必须由用户主动确认。"
                        ),
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
        return tasks
