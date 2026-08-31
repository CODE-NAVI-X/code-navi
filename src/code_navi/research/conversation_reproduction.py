"""LLM-authored reproduction plans bounded to a user-selected evidence bundle."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ExperimentEvidenceBundle,
    PaperReadingEvidence,
    ReproductionConditions,
    ReproductionPipeline,
    ReproductionPipelineItem,
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
    "full_text_user_triggered",
    "user_submitted_text_unverified",
    "user_provided_conditions",
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
    paper_reading: PaperReadingEvidence | None = None,
    conditions: ReproductionConditions | None = None,
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
            "paper_reading": paper_reading.model_dump(mode="json") if paper_reading else None,
            "user_conditions": conditions.model_dump(mode="json") if conditions else None,
            "writing_guidance": [
                "用户提供的复现条件（user_conditions）是唯一硬件/时间/目标来源："
                "把 hardware、available_time、reproduction_goal 等已提供内容写进 resources 和 "
                "reproduction_goal，来源标注为 user_provided_conditions；"
                "用户未提供的设备、数据规模或训练时长一律保持 to_verify，"
                "不得假设 CUDA 或具体配置。",
                "围绕当前选中的论文和用户研究目标，写一份可实际执行的专业复现方案，"
                "不要只给关键词、短句或泛泛的任务清单。",
                "每个 content 应写成连续的完整段落；至少说明目标、具体操作顺序、输入与输出、"
                "参数依据、预期观察和判定标准。允许使用多句话和换行，不要为了简短压缩成一行。",
                "实验步骤要覆盖环境准备、数据处理、基线/主方法运行、指标记录、对照与失败记录，"
                "并说明每一步完成后如何判断可以进入下一步。",
                "论文正文或摘要没有明确给出的超参数、数据划分、Accuracy、硬件需求和结论"
                "必须标记为 to_verify，"
                "不得为了让方案看起来完整而自行补齐。",
                "优先给出适合当前设备和时间约束的最小可行路径，同时解释删减会影响什么；"
                "不要声称系统已经下载数据、配置环境、运行代码或完成复现。",
            ],
            "source_boundary": {
                "allowed_scopes": sorted(_ALLOWED_SCOPES),
                "forbidden": [
                    "代码仓库、数据文件和真实运行日志均未提供给模型。",
                    "如果提供 paper_reading，只能引用其中提取的论文正文片段。",
                    "不得声称数据已下载、环境已配置、代码已运行或复现已成功。",
                    "没有来源的 Accuracy、数据划分、超参数、资源需求必须为 to_verify。",
                ],
            },
            "required_json_shape": {
                "schema_version": "reproduction-pipeline.v1",
                "required_fields": [
                    "schema_version",
                    "pipeline_id",
                    "conversation_id",
                    "source_bundle_id",
                    "selected_paper",
                    "reproduction_goal",
                    "research_question",
                    "known_method",
                    "data_and_sample_conditions",
                    "candidate_baselines",
                    "metrics",
                    "experiment_steps",
                    "resources",
                    "risks",
                    "ethics",
                    "acceptance_criteria",
                    "confirmation_items",
                    "tasks",
                    "two_week_mvp",
                    "created_at",
                    "provenance_note",
                ],
                "selected_paper_shape": {
                    "url": "copy the selected paper url exactly",
                    "title": "copy the selected paper title exactly",
                    "source_name": "string",
                    "year": "integer or null",
                    "identifier": "string or null",
                    "abstract_scope": "metadata_only|metadata_and_abstract",
                    "abstract_excerpt": "string or null",
                },
                "item_shape": {
                    "content": (
                        "detailed multi-sentence paragraph with explicit steps "
                        "and acceptance criteria"
                    ),
                    "classification": "inference|to_verify",
                    "basis": "string",
                    "source_scope": "one allowed source scope",
                },
                "task_shape": {
                    "task_id": "lowercase stable slug",
                    "title": "string",
                    "description": "string",
                    "classification": "inference|to_verify",
                    "basis": "string",
                    "source_scope": "one allowed source scope",
                    "status": "not_started",
                    "evidence_links": [],
                },
                "forbidden_top_level_fields": ["artifacts", "notes"],
                "forbidden_task_fields": ["task_type"],
                "list_fields": [
                    "data_and_sample_conditions",
                    "candidate_baselines",
                    "metrics",
                    "experiment_steps",
                    "resources",
                    "risks",
                    "ethics",
                    "acceptance_criteria",
                    "confirmation_items",
                    "tasks",
                    "two_week_mvp",
                ],
                "identity_fields": {
                    "pipeline_id": "string placeholder",
                    "conversation_id": "string placeholder, never null",
                    "source_bundle_id": "string",
                    "created_at": "ISO-8601 datetime string",
                },
                "task_status_and_evidence_links": "will be recomputed by the application",
                "rules": [
                    "Return exactly one complete JSON object with the required fields above.",
                    "Do not return a simplified plan, artifacts/notes object, Markdown, "
                    "or extra fields.",
                    "Copy the selected_paper url and title exactly from the selected "
                    "evidence bundle.",
                ],
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
    condition_items = _user_condition_items(conditions)
    resources = [*condition_items, *generated.resources]
    goal = generated.reproduction_goal
    if conditions is not None and (conditions.reproduction_goal or "").strip():
        goal = generated.reproduction_goal.model_copy(
            update={
                "content": conditions.reproduction_goal or "",
                "classification": "fact",
                "basis": "用户在复现条件中提供。",
                "source_scope": "user_provided_conditions",
            }
        )
    acceptance = generated.acceptance_criteria
    if not acceptance:
        acceptance = [
            ReproductionPipelineItem(
                content=(
                    "验收条件尚未有来源覆盖：以论文原始基线为参照，"
                    "数据划分、超参数与 Accuracy 数值均待正文或真实运行核验。"
                ),
                classification="to_verify",
                basis="程序补充的待核验占位；模型未提供验收条件时不代替来源。",
                source_scope="profile_and_plan_only",
            )
        ]
    return generated.model_copy(
        update={
            "pipeline_id": identifier,
            "conversation_id": bundle.conversation_id,
            "source_bundle_id": bundle.bundle_id,
            "selected_paper": _selected_paper(generated, paper),
            "reproduction_goal": goal,
            "resources": resources,
            "acceptance_criteria": acceptance,
            "tasks": _attach_user_evidence(generated.tasks, experiment_evidence),
            "created_at": now,
            "generation_mode": "llm",
            "run_id": outcome.run_id,
            "event_count": outcome.event_count,
            "paper_reading": paper_reading,
            "provenance_note": (
                "本复现方案由模型基于当前科研画像、计划、用户主动选择的论文以及"
                f"{'用户显式提供的公开 PDF 正文片段和' if paper_reading else '论文元数据/摘要和'}"
                "用户提交实验记录生成。规则程序已校验来源归属、身份与事实边界；"
                "系统未下载代码或数据、执行训练，也不代表复现成功。"
            ),
        }
    )


def _user_condition_items(
    conditions: ReproductionConditions | None,
) -> list[ReproductionPipelineItem]:
    """User-provided conditions enter the plan as user-sourced facts."""
    if conditions is None:
        return []
    labels = (
        ("硬件", conditions.hardware),
        ("显存", conditions.vram),
        ("操作系统", conditions.operating_system),
        ("Python 环境", conditions.python_environment),
        ("可用时间", conditions.available_time),
    )
    items = [
        ReproductionPipelineItem(
            content=f"{label}：{value}",
            classification="fact",
            basis="用户在复现条件中提供。",
            source_scope="user_provided_conditions",
        )
        for label, value in labels
        if (value or "").strip()
    ]
    return items


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
