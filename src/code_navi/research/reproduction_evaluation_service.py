"""Persistence and orchestration for user-triggered reproduction evaluations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from .conversation_schemas import ExperimentEvidenceBundle, ResearchProfile, SelectedCitation
from .conversation_service import ConversationNotFoundError
from .models import (
    ResearchConversationModel,
    ResearchExperimentEvidenceBundleModel,
    ResearchReproductionEvaluationModel,
    ResearchReproductionImprovementTaskModel,
    ResearchSelectedCitationModel,
)
from .reproduction_evaluation import evaluate_reproduction_project
from .reproduction_evaluation_schemas import (
    ReproductionEvaluationDimensionResult,
    ReproductionImprovementTask,
    ReproductionPipelineEvaluationView,
    ReproductionProjectEvaluation,
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


class UnavailableReproductionPipelineReader:
    """Safe default until A's persisted ReproductionPipeline contract is merged."""

    def load(
        self,
        conversation_id: str,
        db: Session,
    ) -> ReproductionPipelineEvaluationView | None:
        del conversation_id, db
        return None


class ReproductionEvaluationService:
    """Build and restore offline evaluations without executing or retrieving anything."""

    def __init__(self, pipeline_reader: ReproductionPipelineReader | None = None) -> None:
        self.pipeline_reader = pipeline_reader or UnavailableReproductionPipelineReader()

    def create(
        self,
        conversation_id: str,
        db: Session,
    ) -> ReproductionProjectEvaluation:
        """Persist one immutable evaluation snapshot after an explicit user action."""
        conversation = db.get(ResearchConversationModel, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        profile = ResearchProfile.model_validate(conversation.profile_data)
        citations = self._selected_citations(conversation_id, db)
        experiment_bundles = self._experiment_bundles(conversation_id, db)
        pipeline = self.pipeline_reader.load(conversation_id, db)
        dimensions, score_summary = evaluate_reproduction_project(
            profile,
            citations,
            experiment_bundles,
            pipeline,
        )
        created_at = datetime.now(UTC)
        evaluation_id = str(uuid.uuid4())
        tasks = self._build_tasks(
            evaluation_id,
            conversation_id,
            dimensions,
            created_at,
        )
        evaluation = ReproductionProjectEvaluation(
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
            score_summary=score_summary,
            dimensions=dimensions,
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
    ) -> list[ReproductionProjectEvaluation]:
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
    ) -> ReproductionProjectEvaluation:
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
    ) -> ReproductionProjectEvaluation:
        tasks = (
            db.query(ResearchReproductionImprovementTaskModel)
            .filter(
                ResearchReproductionImprovementTaskModel.evaluation_id == record.id
            )
            .order_by(ResearchReproductionImprovementTaskModel.created_at.asc())
            .all()
        )
        return ReproductionProjectEvaluation.model_validate(
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
