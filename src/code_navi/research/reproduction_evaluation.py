"""Deterministic, offline evaluation of saved paper reproduction evidence."""

from __future__ import annotations

from collections.abc import Iterable

from .conversation_schemas import (
    ExperimentEvidenceBundle,
    ResearchProfile,
    SelectedCitation,
)
from .reproduction_evaluation_schemas import (
    ReproductionEvaluationDimensionResult,
    ReproductionEvaluationEvidence,
    ReproductionEvaluationScoreSummary,
    ReproductionPipelineEvaluationView,
)

_PROFILE_SCOPE = "用户已保存科研画像"
_ABSTRACT_SCOPE = "已保存元数据与摘要范围；不包含论文全文"
_EXPERIMENT_SCOPE = "用户主动提交的实验文本；系统未运行代码或复核原始数据"
_PIPELINE_SCOPE = "A 的 ReproductionPipeline 通过只读适配器提供的结构化条目"


def evaluate_reproduction_project(
    profile: ResearchProfile,
    selected_citations: list[SelectedCitation],
    experiment_bundles: list[ExperimentEvidenceBundle],
    pipeline: ReproductionPipelineEvaluationView | None,
) -> tuple[list[ReproductionEvaluationDimensionResult], ReproductionEvaluationScoreSummary]:
    """Return five evidence-bounded dimensions and an honest score denominator."""
    active_citations = [item for item in selected_citations if item.status != "skipped"]
    dimensions = [
        _research_definition(profile, pipeline),
        _source_traceability(active_citations, pipeline),
        _reproduction_plan(pipeline),
        _execution_evidence(experiment_bundles),
        _reflection_and_compliance(profile, experiment_bundles, pipeline),
    ]
    scored = [item for item in dimensions if item.score is not None]
    earned = sum(item.score or 0 for item in scored)
    maximum = len(scored) * 20
    return dimensions, ReproductionEvaluationScoreSummary(
        earned_score=earned,
        scored_maximum=maximum,
        scored_dimension_count=len(scored),
        unscored_dimension_count=5 - len(scored),
        display=(
            f"{earned}/{maximum}（当前有 {5 - len(scored)} 个维度因证据不足未评分；"
            "完整结构上限为 100）"
            if maximum
            else "暂无可评分维度；完整结构上限为 100"
        ),
    )


def _research_definition(
    profile: ResearchProfile,
    pipeline: ReproductionPipelineEvaluationView | None,
) -> ReproductionEvaluationDimensionResult:
    checks = [
        bool(profile.topic),
        bool(profile.research_questions),
        bool(profile.context),
        bool(profile.expected_output),
        bool(pipeline and pipeline.objective_entries),
    ]
    score = sum(checks) * 4
    issues: list[str] = []
    suggestions: list[str] = []
    if not profile.topic:
        issues.append("研究主题尚未明确。")
        suggestions.append("补充明确、可识别的复现主题。")
    if not profile.research_questions:
        issues.append("尚未形成优先研究问题。")
        suggestions.append("确认本次复现要验证的核心问题。")
    if not profile.context:
        issues.append("应用场景或对象范围尚未保存。")
    if not profile.expected_output:
        issues.append("预期交付物尚未保存。")
    if pipeline is None:
        issues.append("当前会话尚未保存 ReproductionPipeline，无法核对复现目标映射。")
        suggestions.append("先选择已保存论文并主动生成复现方案，再重新运行本评估。")
    evidence = _profile_evidence(profile)
    if pipeline:
        evidence.extend(_pipeline_evidence(pipeline.objective_entries, pipeline.pipeline_id))
    return _dimension(
        "research_definition",
        "问题与目标定义",
        score,
        issues,
        evidence,
        "只确认用户画像与 Pipeline 中显式保存的目标；不判断研究问题是否新颖或正确。",
        issues,
        suggestions,
    )


def _source_traceability(
    citations: list[SelectedCitation],
    pipeline: ReproductionPipelineEvaluationView | None,
) -> ReproductionEvaluationDimensionResult:
    if not citations:
        return _unscored(
            "source_traceability",
            "论文与来源可追溯性",
            "尚无用户明确保留的论文来源。",
            "没有来源时不能推断论文内容、复现对象或证据完整性。",
            "先从已保存 EvidenceBundle 中明确选择目标论文或支持来源。",
        )
    unique_urls = {item.citation.url.casefold() for item in citations}
    complete = [item for item in citations if item.citation.metadata_completeness == "complete"]
    abstract = [
        item
        for item in citations
        if item.citation.abstract_scope == "metadata_and_abstract"
    ]
    mapped = [item for item in citations if item.target_section and item.paragraph_anchor]
    score = min(
        20,
        4
        + min(len(unique_urls), 3) * 2
        + (4 if complete else 0)
        + (3 if abstract else 0)
        + (3 if mapped else 0),
    )
    issues: list[str] = []
    verify: list[str] = []
    if not complete:
        issues.append("已选来源仍存在作者、年份或标识符等元数据缺口。")
    if len(abstract) < len(citations):
        verify.append("部分来源只有元数据，不能用于支持摘要范围内的具体表述。")
    if (
        pipeline
        and pipeline.target_paper_url
        and pipeline.target_paper_url.casefold() not in unique_urls
    ):
        issues.append("Pipeline 目标论文未出现在当前用户保留的来源中。")
        verify.append("核对 Pipeline 目标论文与已选论文是否为同一来源。")
    evidence = [
        ReproductionEvaluationEvidence(
            source_type="selected_citation",
            source_id=item.selected_citation_id,
            label=item.citation.paper_title,
            classification=item.citation.classification,
            information_scope=(
                _ABSTRACT_SCOPE
                if item.citation.abstract_scope == "metadata_and_abstract"
                else "仅保存元数据；无摘要或全文"
            ),
            basis=f"用户明确选择该来源并映射到“{item.target_section}”。",
        )
        for item in citations[:20]
    ]
    return _dimension(
        "source_traceability",
        "论文与来源可追溯性",
        score,
        issues,
        evidence,
        "来源内容最多覆盖已保存元数据与摘要；摘要之外的实验、数据集和结论不得标为事实。",
        verify,
        ["补齐缺失元数据并人工核对目标论文。"] if issues or verify else [],
    )


def _reproduction_plan(
    pipeline: ReproductionPipelineEvaluationView | None,
) -> ReproductionEvaluationDimensionResult:
    if pipeline is None:
        return _unscored(
            "reproduction_plan",
            "复现路径与可执行性",
            "当前会话尚未保存 ReproductionPipeline，无法评价数据、基线、指标与步骤。",
            "B 不使用普通研究计划冒充论文复现 Pipeline，也不自行重写 A 的规则。",
            "先选择已保存论文并主动生成复现方案，再重新运行本评估。",
        )
    groups = [
        pipeline.dataset_entries,
        pipeline.baseline_entries,
        pipeline.metric_entries,
        pipeline.step_entries,
        pipeline.resource_entries,
    ]
    score = sum(bool(group) for group in groups) * 4
    names = ("数据说明", "基线/对照", "评价指标", "复现步骤", "资源与环境")
    missing = [name for name, group in zip(names, groups, strict=True) if not group]
    evidence = _pipeline_evidence(
        [entry for group in groups for entry in group], pipeline.pipeline_id
    )
    all_unverified = bool(evidence) and all(
        item.classification == "to_verify" for item in evidence
    )
    verification = [f"人工确认{name}与目标论文一致。" for name in missing]
    if all_unverified:
        score = 0
        verification.append(
            "当前 Pipeline 条目均为待核验信息，不能据此声称复现方案已经准备完成。"
        )
    elif any(item.classification == "to_verify" for item in evidence):
        verification.append("人工核对 Pipeline 中标为待验证的条件与来源范围。")
    suggestions = (
        ["先核对 Pipeline 中所有待验证条件的来源。"]
        if all_unverified
        else [f"补充{name}后重新评估。" for name in missing[:3]]
    )
    return _dimension(
        "reproduction_plan",
        "复现路径与可执行性",
        score,
        [f"缺少{name}。" for name in missing],
        evidence,
        "仅检查 Pipeline 条目是否存在且可追溯，不执行代码、不下载数据，也不证明方案可复现。",
        verification,
        suggestions,
    )


def _execution_evidence(
    bundles: list[ExperimentEvidenceBundle],
) -> ReproductionEvaluationDimensionResult:
    if not bundles:
        return _unscored(
            "execution_evidence",
            "执行记录与结果证据",
            "尚无用户主动提交的实验记录。",
            "没有实验记录时本维度必须保持不可评估，系统不会把计划或代码草案当成运行结果。",
            "粘贴实验设置、指标结果、失败日志或表格/图表说明后重新评估。",
        )
    items = [item for bundle in bundles for item in bundle.items]
    categories = {item.category for item in items}
    checks = [
        bool(categories & {"setup", "data_or_sample"}),
        "baseline_or_control" in categories,
        bool(categories & {"metric_or_result", "result_table", "chart_description"}),
        "random_seed_or_reason" in categories,
        "failure_or_limitation" in categories,
    ]
    score = sum(checks) * 4
    expected = {
        "实验设置或数据说明": checks[0],
        "基线或对照记录": checks[1],
        "指标或结果记录": checks[2],
        "随机种子或不可得原因": checks[3],
        "失败、异常或局限记录": checks[4],
    }
    missing = [name for name, exists in expected.items() if not exists]
    evidence = [
        ReproductionEvaluationEvidence(
            source_type="experiment_evidence",
            source_id=bundle.bundle_id,
            label=f"{bundle.experiment_name.content}：{item.category}",
            classification=item.classification,
            information_scope=_EXPERIMENT_SCOPE,
            basis=item.basis,
        )
        for bundle in bundles
        for item in bundle.items
    ][:30]
    return _dimension(
        "execution_evidence",
        "执行记录与结果证据",
        score,
        [f"缺少{name}。" for name in missing],
        evidence,
        "fact 只表示用户报告事实；系统未读取原始数据、运行代码或独立复核结果。",
        [f"核对并补充{name}。" for name in missing],
        [f"补充{name}。" for name in missing[:3]],
    )


def _reflection_and_compliance(
    profile: ResearchProfile,
    bundles: list[ExperimentEvidenceBundle],
    pipeline: ReproductionPipelineEvaluationView | None,
) -> ReproductionEvaluationDimensionResult:
    items = [item for bundle in bundles for item in bundle.items]
    has_failure = any(item.category == "failure_or_limitation" for item in items)
    has_ethics = any(item.category == "ethics_or_data_governance" for item in items)
    has_pending = any(item.category == "pending_item" for item in items)
    has_constraints = bool(profile.constraints or profile.uncertainties)
    has_pipeline_risks = bool(pipeline and (pipeline.risk_entries or pipeline.ethics_entries))
    if not any((has_failure, has_ethics, has_pending, has_constraints, has_pipeline_risks)):
        return _unscored(
            "reflection_and_compliance",
            "局限、伦理与迭代记录",
            "尚无局限、伦理、风险或待办记录。",
            "系统不能从沉默推断不存在失败、伦理风险或后续工作。",
            "补充失败日志、限制条件、数据许可/伦理说明和下一轮待办。",
        )
    checks = [has_failure, has_ethics, has_pending, has_constraints, has_pipeline_risks]
    score = sum(checks) * 4
    missing_labels = [
        label
        for label, exists in zip(
            ("失败或局限", "伦理与数据治理", "下一轮待办", "约束或不确定性", "Pipeline 风险"),
            checks,
            strict=True,
        )
        if not exists
    ]
    evidence = [
        ReproductionEvaluationEvidence(
            source_type="experiment_evidence",
            source_id=bundle.bundle_id,
            label=item.content,
            classification=item.classification,
            information_scope=_EXPERIMENT_SCOPE,
            basis=item.basis,
        )
        for bundle in bundles
        for item in bundle.items
        if item.category in {"failure_or_limitation", "ethics_or_data_governance", "pending_item"}
    ][:20]
    evidence.extend(_profile_constraint_evidence(profile))
    if pipeline:
        evidence.extend(
            _pipeline_evidence(
                [*pipeline.risk_entries, *pipeline.ethics_entries], pipeline.pipeline_id
            )
        )
    return _dimension(
        "reflection_and_compliance",
        "局限、伦理与迭代记录",
        score,
        [f"缺少{label}记录。" for label in missing_labels],
        evidence[:30],
        "只检查记录是否存在及其来源边界，不判断伦理审批已通过或风险已经消除。",
        [f"人工确认并补充{label}。" for label in missing_labels],
        [f"补充{label}记录。" for label in missing_labels[:3]],
    )


def _dimension(
    dimension: str,
    label: str,
    score: int,
    issues: list[str],
    evidence: list[ReproductionEvaluationEvidence],
    boundary: str,
    to_verify: list[str],
    suggestions: list[str],
) -> ReproductionEvaluationDimensionResult:
    status = (
        "needs_revision"
        if score <= 8
        else "evidence_partial"
        if score <= 15 or issues or to_verify
        else "checklist_complete"
    )
    return ReproductionEvaluationDimensionResult(
        dimension=dimension,
        label=label,
        status=status,
        score=score,
        issues=_unique(issues),
        evidence=evidence,
        fact_boundary=boundary,
        to_verify=_unique(to_verify),
        next_suggestions=_unique(suggestions),
    )


def _unscored(
    dimension: str,
    label: str,
    issue: str,
    boundary: str,
    suggestion: str,
) -> ReproductionEvaluationDimensionResult:
    return ReproductionEvaluationDimensionResult(
        dimension=dimension,
        label=label,
        status="not_evaluable",
        score=None,
        issues=[issue],
        fact_boundary=boundary,
        to_verify=[issue],
        next_suggestions=[suggestion],
    )


def _profile_evidence(profile: ResearchProfile) -> list[ReproductionEvaluationEvidence]:
    values = [
        ("研究主题", profile.topic),
        ("研究问题", "；".join(profile.research_questions)),
        ("对象与场景", profile.context),
        ("预期产出", profile.expected_output),
    ]
    return [
        ReproductionEvaluationEvidence(
            source_type="research_profile",
            label=f"{label}：{value}",
            classification="fact",
            information_scope=_PROFILE_SCOPE,
            basis="来自当前会话中用户已保存的科研画像。",
        )
        for label, value in values
        if value
    ]


def _profile_constraint_evidence(
    profile: ResearchProfile,
) -> list[ReproductionEvaluationEvidence]:
    return [
        ReproductionEvaluationEvidence(
            source_type="research_profile",
            label=value,
            classification="to_verify",
            information_scope=_PROFILE_SCOPE,
            basis="来自科研画像中的约束或不确定性，仍需用户、导师或项目记录核对。",
        )
        for value in [*profile.constraints, *profile.uncertainties]
    ][:12]


def _pipeline_evidence(entries: Iterable, pipeline_id: str) -> list[ReproductionEvaluationEvidence]:
    return [
        ReproductionEvaluationEvidence(
            source_type="reproduction_pipeline",
            source_id=pipeline_id,
            label=entry.content,
            classification=entry.classification,
            information_scope=entry.source_scope or _PIPELINE_SCOPE,
            basis=entry.basis,
        )
        for entry in entries
    ][:30]


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
