"""LLM-authored reproduction plans bounded to a user-selected evidence bundle."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ExperimentEvidenceBundle,
    ReproductionPipeline,
    ReproductionSelectedPaper,
    ReproductionTask,
    ReproductionTaskEvidenceLink,
    ResearchProfile,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact
from .schemas import AcademicPaperResult

_ALLOWED_SCOPES = {
    "profile_and_plan_only",
    "metadata_and_abstract_only",
    "user_submitted_text_unverified",
}
_TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,98}$")


def build_reproduction_pipeline(
    profile: ResearchProfile,
    plan: ConversationResearchPlan | None,
    bundle: ConversationEvidenceBundle,
    paper: AcademicPaperResult,
    experiment_evidence: list[ExperimentEvidenceBundle],
    *,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
    pipeline_id: str | None = None,
    created_at: datetime | None = None,
) -> ReproductionPipeline:
    """Create a model-written plan without granting it identity or evidence authority."""
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "reproduction_pipeline: generator is unavailable"
        )
    resolved_conversation_id = conversation_id or bundle.conversation_id
    if resolved_conversation_id != bundle.conversation_id:
        raise ValueError("selected evidence bundle belongs to a different conversation")

    outcome = generator.generate(
        kind="reproduction_pipeline",
        conversation_id=resolved_conversation_id,
        context={
            "research_profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json") if plan else None,
            "selected_evidence_bundle": {
                "bundle_id": bundle.bundle_id,
                "query": bundle.query,
                "provenance_note": bundle.provenance_note,
                "paper": paper.model_dump(mode="json"),
            },
            "experiment_evidence": [
                item.model_dump(mode="json") for item in experiment_evidence
            ],
            "source_boundary": {
                "allowed_scopes": sorted(_ALLOWED_SCOPES),
                "forbidden": [
                    "论文全文、代码仓库、数据文件和真实运行日志均未提供给模型。",
                    "不得声称数据已下载、环境已配置、代码已运行或复现已成功。",
                    "没有来源的 Accuracy、数据划分、超参数、资源需求必须为 to_verify。",
                ],
            },
            "required_json_shape": {
                "schema_version": "reproduction-pipeline.v1",
                "all_fields": "Return a complete ReproductionPipeline JSON object.",
                "item_classification": "inference|to_verify only",
                "task_id": "lowercase stable slug; tasks are suggestions, not executions",
                "task_status_and_evidence_links": "will be recomputed by the application",
            },
        },
    )
    try:
        generated = ReproductionPipeline.model_validate_json(
            require_generated_artifact(outcome, kind="reproduction_pipeline")
        )
        _validate_generated_pipeline(generated, paper)
    except ResearchGenerationError:
        raise
    except ValueError as error:
        raise ResearchGenerationError(
            "invalid_output", "reproduction_pipeline: boundary validation failed"
        ) from error

    now = created_at or datetime.now(UTC)
    identifier = pipeline_id or _stable_id(bundle.bundle_id, paper.url)
    return generated.model_copy(
        update={
            "pipeline_id": identifier,
            "conversation_id": bundle.conversation_id,
            "source_bundle_id": bundle.bundle_id,
            "selected_paper": _selected_paper(generated, paper),
            "tasks": _attach_user_evidence(generated.tasks, experiment_evidence),
            "created_at": now,
            "generation_mode": "llm",
            "run_id": outcome.run_id,
            "event_count": outcome.event_count,
            "provenance_note": (
                "本复现方案由模型基于当前科研画像、计划、用户主动选择的论文元数据/摘要和"
                "用户提交实验记录生成。规则程序已校验来源归属、身份与事实边界；"
                "系统未读取全文、下载代码或数据、执行训练，也不代表复现成功。"
            ),
        }
    )


def _selected_paper(
    generated: ReproductionPipeline, paper: AcademicPaperResult
) -> ReproductionSelectedPaper:
    """Return the application-owned identity; model text cannot replace it."""
    selected = generated.selected_paper
    if selected.url != paper.url or selected.title != paper.title:
        raise ValueError("model changed the user-selected paper identity")
    return selected.model_copy(
        update={
            "source_name": paper.source_name,
            "year": paper.year,
            "identifier": paper.identifier,
            "abstract_scope": "metadata_and_abstract"
            if paper.abstract_excerpt
            else "metadata_only",
            "abstract_excerpt": paper.abstract_excerpt,
        }
    )


def _validate_generated_pipeline(
    pipeline: ReproductionPipeline, paper: AcademicPaperResult
) -> None:
    _selected_paper(pipeline, paper)
    entries = [
        pipeline.reproduction_goal,
        pipeline.research_question,
        pipeline.known_method,
        *pipeline.data_and_sample_conditions,
        *pipeline.candidate_baselines,
        *pipeline.metrics,
        *pipeline.experiment_steps,
        *pipeline.resources,
        *pipeline.risks,
        *pipeline.ethics,
        *pipeline.confirmation_items,
        *pipeline.two_week_mvp,
    ]
    if any(item.classification == "fact" for item in entries):
        raise ValueError("model cannot introduce fact-classified reproduction guidance")
    if any(item.source_scope not in _ALLOWED_SCOPES for item in entries):
        raise ValueError("model used an unsupported reproduction source scope")
    if not pipeline.tasks or len({task.task_id for task in pipeline.tasks}) != len(
        pipeline.tasks
    ):
        raise ValueError("model must provide distinct reproduction tasks")
    if any(
        task.classification == "fact"
        or task.source_scope not in _ALLOWED_SCOPES
        or not _TASK_ID.fullmatch(task.task_id)
        for task in pipeline.tasks
    ):
        raise ValueError("model produced an invalid reproduction task boundary")


def _attach_user_evidence(
    tasks: list[ReproductionTask], experiment_evidence: list[ExperimentEvidenceBundle]
) -> list[ReproductionTask]:
    return [
        task.model_copy(
            update={
                "status": "evidence_linked"
                if (links := _task_links(task.task_id, experiment_evidence))
                else "not_started",
                "evidence_links": links,
            }
        )
        for task in tasks
    ]


def _task_links(
    task_id: str, experiment_evidence: list[ExperimentEvidenceBundle]
) -> list[ReproductionTaskEvidenceLink]:
    links: list[ReproductionTaskEvidenceLink] = []
    for bundle in experiment_evidence:
        for item in [bundle.experiment_name, bundle.goal, *bundle.items]:
            if item.related_plan_item == task_id:
                links.append(
                    ReproductionTaskEvidenceLink(
                        experiment_bundle_id=bundle.bundle_id,
                        content=item.content,
                        classification=item.classification,
                    )
                )
    return links


def _stable_id(bundle_id: str, paper_url: str) -> str:
    digest = hashlib.sha256(f"{bundle_id}|{paper_url}".encode()).hexdigest()[:16]
    return f"reproduction-{digest}"
