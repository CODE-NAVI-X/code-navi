"""Rules-only reproduction Pipeline construction from already saved local evidence."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ExperimentEvidenceBundle,
    ReproductionPipeline,
    ReproductionPipelineItem,
    ReproductionSelectedPaper,
    ReproductionTask,
    ReproductionTaskEvidenceLink,
    ResearchProfile,
)
from .schemas import AcademicPaperResult

_ABSTRACT_GAP_SCOPE = "已保存论文仅提供元数据与摘要；摘要/元数据未覆盖该信息。"


def build_reproduction_pipeline(
    profile: ResearchProfile,
    plan: ConversationResearchPlan | None,
    bundle: ConversationEvidenceBundle,
    paper: AcademicPaperResult,
    experiment_evidence: list[ExperimentEvidenceBundle],
    *,
    pipeline_id: str | None = None,
    created_at: datetime | None = None,
) -> ReproductionPipeline:
    """Build a local learning scaffold without searching, reading files, or executing code."""
    now = created_at or datetime.now(UTC)
    identifier = pipeline_id or _stable_id(bundle.bundle_id, paper.url)
    question = next(iter(profile.research_questions or profile.candidate_questions), None)
    selected = ReproductionSelectedPaper(
        url=paper.url,
        title=paper.title,
        source_name=paper.source_name,
        year=paper.year,
        identifier=paper.identifier,
        abstract_excerpt=paper.abstract_excerpt,
    )
    goal = _inference(
        f"建议围绕“{question or profile.topic or paper.title}”定义可确认的复现目标。",
        f"已保存研究画像与用户选择的论文：{paper.title}",
    )
    known_method = _fact(
        paper.abstract_excerpt or f"已保存元数据确认论文标题为《{paper.title}》。",
        "用户选择的论文摘要或元数据原文；不将摘要外内容当作事实。",
    )
    gap = _verify("数据集、样本范围与获取条件待作者、导师或原文核对。")
    plan_entries = plan.candidate_methods_or_baselines if plan else []
    baselines = [_inference(entry.content, entry.basis) for entry in plan_entries[:3]] or [
        _verify("候选基线尚待确认，不能从摘要外补造。")
    ]
    metrics = [_verify("主指标、比较条件与成功阈值待确认，不能由摘要外推。")]
    tasks = _tasks(experiment_evidence)
    two_week_mvp = [
        _inference(entry.content, entry.basis) for entry in (plan.two_week_mvp_plan if plan else [])
    ] or [_verify("两周 MVP 的范围、投入和产出待用户确认。")]
    return ReproductionPipeline(
        pipeline_id=identifier,
        conversation_id=bundle.conversation_id,
        source_bundle_id=bundle.bundle_id,
        selected_paper=selected,
        reproduction_goal=goal,
        research_question=_inference(
            question or "研究问题尚待确认，不能由论文标题替代。",
            f"已保存研究画像：{profile.topic or '主题尚待确认'}",
        ),
        known_method=known_method,
        data_and_sample_conditions=[gap],
        candidate_baselines=baselines,
        metrics=metrics,
        experiment_steps=[
            _inference(
                "先记录可用输入、比较对象与输出，再由用户手动提交实验记录。", "本地学习脚手架。"
            ),
            _verify("具体实验设置、随机种子和复现条件待核对。"),
        ],
        resources=[_verify("设备、运行环境、数据授权与时间投入待确认。")],
        risks=[_verify("摘要不足以证明可复现性；需记录失败原因和限制。")],
        ethics=[_verify("数据治理、隐私与伦理要求待作者、导师或机构确认。")],
        confirmation_items=[_verify("确认数据、基线、指标、资源和伦理边界后再进行人工实验。")],
        tasks=tasks,
        two_week_mvp=two_week_mvp,
        created_at=now,
        provenance_note=(
            "本复现 Pipeline 只读取已保存的研究画像、规则计划、"
            "受限论文元数据/摘要和用户提交的实验记录；"
            "不联网、不下载全文、不生成或执行代码、不写入学生项目，也不代表已复现成功。"
        ),
    )


def _tasks(experiment_evidence: list[ExperimentEvidenceBundle]) -> list[ReproductionTask]:
    definitions = (
        (
            "confirm-python-environment",
            "确认 Python 学习环境",
            "列出解释器、依赖版本和可用资源，作为用户手动核对项。",
        ),
        (
            "compare-python-baseline",
            "比较候选基线",
            "用可拆分的 Python 实验步骤记录一个基线或对照条件；系统不会生成或运行完整代码。",
        ),
        (
            "record-results-and-failures",
            "记录结果与失败原因",
            "用户主动粘贴结果、失败原因和待确认项，不把建议当作实验事实。",
        ),
    )
    tasks: list[ReproductionTask] = []
    for task_id, title, description in definitions:
        links = _task_links(task_id, experiment_evidence)
        tasks.append(
            ReproductionTask(
                task_id=task_id,
                title=title,
                description=description,
                classification="inference",
                basis="规则生成的 Python 学习脚手架，不含可执行代码。",
                source_scope="规则计划与用户提交实验记录的任务关联。",
                status="evidence_linked" if links else "not_started",
                evidence_links=links,
            )
        )
    return tasks


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


def _fact(content: str, basis: str) -> ReproductionPipelineItem:
    return ReproductionPipelineItem(
        content=content,
        classification="fact",
        basis=basis,
        source_scope="已保存论文元数据或摘要范围。",
    )


def _inference(content: str, basis: str) -> ReproductionPipelineItem:
    return ReproductionPipelineItem(
        content=content,
        classification="inference",
        basis=basis,
        source_scope="已保存研究画像与规则计划范围。",
    )


def _verify(content: str) -> ReproductionPipelineItem:
    return ReproductionPipelineItem(
        content=content,
        classification="to_verify",
        basis="系统不读取论文全文或执行实验，不能补造细节。",
        source_scope=_ABSTRACT_GAP_SCOPE,
    )


def _stable_id(bundle_id: str, paper_url: str) -> str:
    digest = hashlib.sha256(f"{bundle_id}|{paper_url}".encode()).hexdigest()[:16]
    return f"reproduction-{digest}"
