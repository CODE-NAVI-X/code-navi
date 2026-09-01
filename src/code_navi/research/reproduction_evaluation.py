from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import urlparse

from .conversation_schemas import (
    ExperimentEvidenceBundle,
    ResearchProfile,
    SelectedCitation,
)
from .metrics_catalog import find_standard_metric
from .reproduction_evaluation_schemas import (
    ReproductionEvaluationCriterion,
    ReproductionEvaluationDimensionResult,
    ReproductionEvaluationEvidence,
    ReproductionEvaluationScoreSummary,
    ReproductionImprovementTask,
    ReproductionPipelineEvaluationView,
)

_PROFILE_SCOPE = "用户已保存科研画像"
_ABSTRACT_SCOPE = "已保存元数据与摘要范围；不包含论文全文"
_EXPERIMENT_SCOPE = "用户主动提交的实验文本；系统未运行代码或复核原始数据"
_PIPELINE_SCOPE = "A 的 ReproductionPipeline 通过只读适配器提供的结构化条目"


def evaluate_reproduction_project_v2(
    profile: ResearchProfile,
    selected_citations: list[SelectedCitation],
    experiment_bundles: list[ExperimentEvidenceBundle],
    pipeline: ReproductionPipelineEvaluationView | None,
    *,
    conversation_id: str,
    evaluation_id: str,
    created_at: datetime | None = None,
) -> tuple[list[ReproductionEvaluationCriterion], int, list[ReproductionImprovementTask]]:
    """Return six 2-point criteria (total 12) with traceable basis and linked improvement tasks."""
    now = created_at or datetime.now(UTC)
    active_citations = [item for item in selected_citations if item.status != "skipped"]

    # 1. 研究问题与假设可复述性
    c1, c1_sugg = _criterion_research_question(profile, pipeline)
    # 2. 方法可执行性（步骤完整、变量可操作）
    c2, c2_sugg = _criterion_method_executability(pipeline)
    # 3. 数据可得性（公开链接与许可）
    c3, c3_sugg = _criterion_data_availability(active_citations, pipeline)
    # 4. 指标与统计方法正确性
    c4, c4_sugg = _criterion_metrics_correctness(pipeline)
    # 5. 计算资源与时间可行性
    c5, c5_sugg = _criterion_resources_feasibility(profile, pipeline)
    # 6. 结果核验路径（baseline 与预期区间）
    c6, c6_sugg = _criterion_results_verification(experiment_bundles, pipeline)

    criteria_with_suggestions = [
        (c1, c1_sugg, "research_definition"),
        (c2, c2_sugg, "reproduction_plan"),
        (c3, c3_sugg, "source_traceability"),
        (c4, c4_sugg, "reproduction_plan"),
        (c5, c5_sugg, "reflection_and_compliance"),
        (c6, c6_sugg, "execution_evidence"),
    ]

    criteria: list[ReproductionEvaluationCriterion] = []
    tasks: list[ReproductionImprovementTask] = []

    for criterion, suggestion, dimension in criteria_with_suggestions:
        if criterion.score < 2 and suggestion:
            task_id = str(uuid.uuid4())
            task = ReproductionImprovementTask(
                task_id=task_id,
                evaluation_id=evaluation_id,
                conversation_id=conversation_id,
                dimension=dimension,
                title=f"改进“{criterion.title}”",
                description=suggestion,
                status="pending",
                classification="to_verify",
                basis=(
                    f"依据第 {criterion.criterion_no} 项标准（{criterion.title}）："
                    f"{criterion.basis}"
                ),
                created_at=now,
                updated_at=now,
            )
            tasks.append(task)
            criterion = criterion.model_copy(update={"improvement_task_id": task_id})
        criteria.append(criterion)

    total_score = sum(c.score for c in criteria)
    return criteria, total_score, tasks


def _criterion_research_question(
    profile: ResearchProfile,
    pipeline: ReproductionPipelineEvaluationView | None,
) -> tuple[ReproductionEvaluationCriterion, str | None]:
    has_topic = bool(profile.topic)
    has_questions = bool(profile.research_questions)
    has_pipeline_goal = bool(pipeline and pipeline.objective_entries)
    evidence = _profile_evidence(profile)
    if pipeline:
        evidence.extend(_pipeline_evidence(pipeline.objective_entries, pipeline.pipeline_id))

    if has_topic and has_questions and has_pipeline_goal:
        score = 2
        basis = (
            "已保存清晰的研究主题与优先研究问题，且复现 Pipeline 包含对应目标条目，"
            "问题与假设具备明确可复述性。"
        )
        suggestion = None
    elif has_topic and has_questions:
        score = 1
        basis = (
            "已保存研究主题与研究问题，但尚未生成或关联完整的复现 Pipeline 目标映射，"
            "可复述性仍待核对。"
        )
        suggestion = "先选择已保存论文并在复现工作台生成对应复现目标方案。"
    else:
        score = 0
        basis = "未保存明确的研究主题或研究问题，研究问题与假设目前无法复述。"
        suggestion = "补充明确的研究主题与优先研究问题。"

    return (
        ReproductionEvaluationCriterion(
            criterion_no=1,
            title="研究问题与假设可复述性",
            score=score,
            basis=basis,
            evidence_refs=evidence[:20],
        ),
        suggestion,
    )


def _get_standard_metrics_catalog() -> set[str] | None:
    """Safely import metrics catalog from PR-B if available, otherwise degrade to None."""
    try:
        from . import metrics_catalog

        std_metrics = getattr(metrics_catalog, "STANDARD_METRICS", None)
        if std_metrics is not None and isinstance(std_metrics, (set, list, tuple)):
            return {str(m).strip().lower() for m in std_metrics}

        catalog_dict = getattr(metrics_catalog, "METRICS_CATALOG", None)
        if isinstance(catalog_dict, dict):
            metrics: set[str] = set()
            for v in catalog_dict.values():
                if isinstance(v, (list, tuple, set)):
                    metrics.update(str(x).strip().lower() for x in v)
            return metrics
        return None
    except (ImportError, AttributeError):
        return None


def _criterion_method_executability(
    pipeline: ReproductionPipelineEvaluationView | None,
) -> tuple[ReproductionEvaluationCriterion, str | None]:
    has_multiple_steps = bool(pipeline and len(pipeline.step_entries) >= 2)
    actionable_keywords = (
        "参数",
        "超参",
        "变量",
        "自变量",
        "因变量",
        "控制变量",
        "学习率",
        "learning rate",
        "lr",
        "batch",
        "epoch",
        "optimizer",
        "优化器",
        "loss",
        "损失",
        "维度",
        "特征",
        "hidden",
        "层数",
        "seed",
        "随机种子",
        "split",
        "划分",
        "权重",
        "weight",
        "threshold",
        "阈值",
        "dropout",
        "temperature",
        "top_p",
        "embedding",
    )
    has_actionable_variables = bool(
        pipeline
        and pipeline.step_entries
        and any(
            any(kw in step.content.lower() for kw in actionable_keywords)
            for step in pipeline.step_entries
        )
    )

    if has_multiple_steps and has_actionable_variables:
        score = 2
        basis = (
            "复现 Pipeline 已保存多步骤完整实验步骤，"
            "且步骤中明确记录了可操作的具体变量、超参数与控制条件。"
        )
        suggestion = None
        evidence = _pipeline_evidence(pipeline.step_entries, pipeline.pipeline_id)  # type: ignore[union-attr]
    elif pipeline and pipeline.step_entries:
        score = 1
        if has_multiple_steps and not has_actionable_variables:
            basis = (
                "复现 Pipeline 已记录多步骤流程，"
                "但步骤中缺少具体可操作的变量、超参数或实验控制条件说明。"
            )
            suggestion = "在复现步骤中明确具体可调节的超参数、变量定义与实验控制条件。"
        else:
            basis = "复现 Pipeline 仅包含单一或部分初步步骤，操作变量与步骤完整性仍需细化补充。"
            suggestion = "细化复现实验步骤并明确可操作的变量与参数。"
        evidence = _pipeline_evidence(pipeline.step_entries, pipeline.pipeline_id)
    else:
        score = 0
        basis = "尚未保存复现实验步骤与方法操作变量，方法当前不具备可执行性依据。"
        suggestion = "先选择已保存论文生成复现方案并补充步骤细节与操作变量。"
        evidence = []

    return (
        ReproductionEvaluationCriterion(
            criterion_no=2,
            title="方法可执行性（步骤完整、变量可操作）",
            score=score,
            basis=basis,
            evidence_refs=evidence[:20],
        ),
        suggestion,
    )


_URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_+.~#?&/=]*"
)
_HOST_REGEX = re.compile(
    r"\b(?:github\.com|huggingface\.co|zenodo\.org|kaggle\.com|doi\.org|gitlab\.com|gitee\.com|osf\.io|figshare\.com)/[^\s]+"
)
_LICENSE_KEYWORDS = (
    "mit",
    "apache",
    "cc-by",
    "cc0",
    "gpl",
    "bsd",
    "public domain",
    "开源许可",
    "开源协议",
    "公开许可",
    "使用许可",
    "共享协议",
    "数据许可",
    "商用许可",
    "学术许可",
    "授权协议",
)


def _extract_valid_url(text: str) -> str | None:
    match = _URL_REGEX.search(text)
    if match:
        url = match.group(0)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return url
    host_match = _HOST_REGEX.search(text)
    if host_match:
        return f"https://{host_match.group(0)}"
    return None


def _has_explicit_license(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _LICENSE_KEYWORDS)


def _criterion_data_availability(
    citations: list[SelectedCitation],
    pipeline: ReproductionPipelineEvaluationView | None,
) -> tuple[ReproductionEvaluationCriterion, str | None]:
    evidence: list[ReproductionEvaluationEvidence] = []
    if citations:
        evidence.extend(
            ReproductionEvaluationEvidence(
                source_type="selected_citation",
                source_id=c.selected_citation_id,
                label=c.citation.paper_title,
                classification=c.citation.classification,
                information_scope=_ABSTRACT_SCOPE,
                basis=f"已选论文来源（非数据集直接下载与许可）：{c.citation.url}",
            )
            for c in citations[:10]
        )
    if pipeline:
        evidence.extend(_pipeline_evidence(pipeline.dataset_entries, pipeline.pipeline_id))

    has_dataset_entries = bool(
        pipeline and (pipeline.dataset_refs or pipeline.dataset_entries)
    )

    # 1. 优先检查上游结构化 DatasetRef
    has_valid_ref = bool(
        pipeline
        and any(
            bool(
                r.url
                and _extract_valid_url(r.url)
                and r.license_note
                and _has_explicit_license(r.license_note)
            )
            for r in pipeline.dataset_refs
        )
    )
    # 2. 检查 dataset_entries 回退条目（同一条目同时包含 URL 与许可）
    has_valid_entry = bool(
        pipeline
        and any(
            bool(_extract_valid_url(d.content) and _has_explicit_license(d.content))
            for d in pipeline.dataset_entries
        )
    )

    if has_valid_ref or has_valid_entry:
        score = 2
        basis = (
            "复现 Pipeline 数据集条目中同一条目已同时记录可核验的公开获取 URL "
            "与明确的数据许可协议。"
        )
        suggestion = None
    elif has_dataset_entries or citations:
        score = 1
        has_any_url = bool(
            pipeline
            and (
                any(r.url and _extract_valid_url(r.url) for r in pipeline.dataset_refs)
                or any(_extract_valid_url(d.content) for d in pipeline.dataset_entries)
            )
        )
        has_any_license = bool(
            pipeline
            and (
                any(
                    r.license_note and _has_explicit_license(r.license_note)
                    for r in pipeline.dataset_refs
                )
                or any(_has_explicit_license(d.content) for d in pipeline.dataset_entries)
            )
        )
        if has_any_url and has_any_license:
            basis = (
                "复现方案中记录了数据集信息，但未在同一数据集条目中同时提供可核验的"
                "公开 URL 与明确许可协议。"
            )
            suggestion = "在同一数据集条目中同时补充数据集的公开获取 URL 与开源/使用许可声明。"
        elif has_any_url and not has_any_license:
            basis = "复现方案中记录了数据集获取 URL，但缺少明确的数据使用/开源许可协议说明。"
            suggestion = "在复现方案中补充数据集的明确开源协议或使用许可说明（如 MIT、CC-BY 等）。"
        elif has_any_license and not has_any_url:
            basis = "复现方案中记录了数据许可说明，但缺少可直接核验的数据集公开获取 URL。"
            suggestion = (
                "在复现方案中补充数据集的公开获取链接（如 Zenodo、HuggingFace、GitHub 等）。"
            )
        elif citations and not has_dataset_entries:
            basis = (
                "已记录论文引用来源，但尚未在 Pipeline 中提供经核验的数据集公开下载链接"
                "与明确许可协议。"
            )
            suggestion = "在复现方案中补充数据集的公开获取 URL 与明确使用许可。"
        else:
            basis = (
                "已记录数据集名称或初步说明，但尚未同时提供可核验的公开获取链接与明确许可协议。"
            )
            suggestion = "在复现方案中同时补充数据集的公开获取 URL 与开源/使用许可声明。"
    else:
        score = 0
        basis = "尚未保存任何数据集条目、公开链接或数据许可记录。"
        suggestion = "从已保存来源或 Pipeline 中指定数据集公开链接与明确使用许可。"

    return (
        ReproductionEvaluationCriterion(
            criterion_no=3,
            title="数据可得性（公开链接与许可）",
            score=score,
            basis=basis,
            evidence_refs=evidence[:20],
        ),
        suggestion,
    )


def _criterion_metrics_correctness(
    pipeline: ReproductionPipelineEvaluationView | None,
) -> tuple[ReproductionEvaluationCriterion, str | None]:
    if pipeline and (pipeline.metric_specs or pipeline.metric_entries):
        evidence = _pipeline_evidence(pipeline.metric_entries, pipeline.pipeline_id)

        # 1. 检查上游结构化 MetricSpec（必须以 find_standard_metric 目录核验结果为准）
        matched_spec = any(
            find_standard_metric(spec.name) is not None
            for spec in pipeline.metric_specs
        )
        # 2. 检查 metric_entries 回退文本
        matched_entry = any(
            find_standard_metric(m.content) is not None
            for m in pipeline.metric_entries
        )

        if matched_spec or matched_entry:
            score = 2
            basis = "复现方案中指定的评估指标命中标准指标目录，度量方法与定义已规范化。"
            suggestion = None
        else:
            score = 1
            basis = (
                "复现方案中已记录指标，但未完全匹配标准指标目录，度量方法待人工核验（to_verify）。"
            )
            suggestion = "核实所选指标（如精确率、召回率、F1、MSE 等）的度量与统计方法定义。"
    else:
        score = 0
        basis = "尚未保存评估指标与统计方法条目，无法验证度量正确性。"
        suggestion = "在复现方案中补充主要评估指标、统计方法与度量范围。"
        evidence = []

    return (
        ReproductionEvaluationCriterion(
            criterion_no=4,
            title="指标与统计方法正确性（对照标准目录）",
            score=score,
            basis=basis,
            evidence_refs=evidence[:20],
        ),
        suggestion,
    )


def _extract_vram_gb(text: str) -> float | None:
    """Extract quantitative VRAM/memory specification in GB from text."""
    t = text.lower()
    gb_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|g|gib)\b", t)
    if gb_match:
        try:
            return float(gb_match.group(1))
        except ValueError:
            pass
    mb_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mb|mib)\b", t)
    if mb_match:
        try:
            return float(mb_match.group(1)) / 1024.0
        except ValueError:
            pass
    tb_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:tb|tib)\b", t)
    if tb_match:
        try:
            return float(tb_match.group(1)) * 1024.0
        except ValueError:
            pass
    vram_keyword_match = re.search(
        r"(?:显存|内存|显卡)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:g|gb)?\b", t
    )
    if vram_keyword_match:
        try:
            return float(vram_keyword_match.group(1))
        except ValueError:
            pass

    # Model name fallback lookup
    model_vram_map = {
        "4090": 24.0,
        "3090": 24.0,
        "a100": 40.0,
        "h100": 80.0,
        "a800": 80.0,
        "h800": 80.0,
        "v100": 16.0,
        "t4": 16.0,
        "3080": 10.0,
        "4080": 16.0,
        "2080": 8.0,
        "1080": 8.0,
    }
    for model, vram in model_vram_map.items():
        if model in t:
            return vram
    return None


def _extract_time_hours(text: str) -> float | None:
    """Extract quantitative time budget in hours from text."""
    t = text.lower()
    chinese_map = {
        "两周": 14 * 24.0,
        "一周": 7 * 24.0,
        "三周": 21 * 24.0,
        "四周": 28 * 24.0,
        "半个月": 15 * 24.0,
        "一个月": 30 * 24.0,
        "两个月": 60 * 24.0,
        "三个月": 90 * 24.0,
        "半年": 180 * 24.0,
        "一天": 24.0,
        "两天": 48.0,
        "三天": 72.0,
        "七天": 7 * 24.0,
    }
    for word, hours in chinese_map.items():
        if word in t:
            return hours

    m_week = re.search(r"(\d+(?:\.\d+)?)\s*(?:周|个?星期|week|weeks|w)\b", t)
    if m_week:
        try:
            return float(m_week.group(1)) * 7 * 24.0
        except ValueError:
            pass

    m_month = re.search(r"(\d+(?:\.\d+)?)\s*(?:月|个?月|month|months)\b", t)
    if m_month:
        try:
            return float(m_month.group(1)) * 30 * 24.0
        except ValueError:
            pass

    m_day = re.search(r"(\d+(?:\.\d+)?)\s*(?:天|日|day|days|d)\b", t)
    if m_day:
        try:
            return float(m_day.group(1)) * 24.0
        except ValueError:
            pass

    m_hour = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|时|hour|hours|h)\b", t)
    if m_hour:
        try:
            return float(m_hour.group(1))
        except ValueError:
            pass

    return None


def _criterion_resources_feasibility(
    profile: ResearchProfile,
    pipeline: ReproductionPipelineEvaluationView | None,
) -> tuple[ReproductionEvaluationCriterion, str | None]:
    evidence: list[ReproductionEvaluationEvidence] = []
    user_vrams = [
        _extract_vram_gb(c)
        for c in (profile.constraints or [])
        if _extract_vram_gb(c) is not None
    ]
    user_vram = max(user_vrams) if user_vrams else None

    user_times = [
        _extract_time_hours(c)
        for c in (profile.constraints or [])
        if _extract_time_hours(c) is not None
    ]
    user_time = max(user_times) if user_times else None

    req_vrams = (
        [
            _extract_vram_gb(r.content)
            for r in pipeline.resource_entries
            if _extract_vram_gb(r.content) is not None
        ]
        if pipeline and pipeline.resource_entries
        else []
    )
    req_vram = max(req_vrams) if req_vrams else None

    req_times = (
        [
            _extract_time_hours(r.content)
            for r in pipeline.resource_entries
            if _extract_time_hours(r.content) is not None
        ]
        if pipeline and pipeline.resource_entries
        else []
    )
    req_time = max(req_times) if req_times else None

    has_comparable_hardware = bool(user_vram is not None and req_vram is not None)
    hardware_feasible = bool(has_comparable_hardware and user_vram >= req_vram)  # type: ignore[operator]

    # 满分 2 分必须同时存在用户时间预算与方案预计耗时，且需求不超过预算
    has_comparable_time = bool(user_time is not None and req_time is not None)
    time_feasible = bool(has_comparable_time and user_time >= req_time)  # type: ignore[operator]

    if profile.constraints:
        evidence.extend(
            ReproductionEvaluationEvidence(
                source_type="research_profile",
                source_id=None,
                label=c,
                classification="fact",
                information_scope=_PROFILE_SCOPE,
                basis="科研画像中填写的资源与时间约束条件。",
            )
            for c in profile.constraints[:5]
        )
    if pipeline:
        evidence.extend(_pipeline_evidence(pipeline.resource_entries, pipeline.pipeline_id))

    if (
        has_comparable_hardware
        and hardware_feasible
        and has_comparable_time
        and time_feasible
    ):
        score = 2
        basis = (
            f"科研画像已记录可用硬件（{user_vram:g}GB 显存）与时间预算（{user_time:g}小时），"
            f"复现方案需求（{req_vram:g}GB 显存，预计耗时 {req_time:g}小时）未超出可用资源与周期，"
            "具备可比实际可行性。"
        )
        suggestion = None
    elif profile.constraints or (pipeline and pipeline.resource_entries):
        score = 1
        if has_comparable_hardware and not hardware_feasible:
            basis = (
                f"复现方案所需显存（{req_vram:g}GB）超出科研画像记录的用户可用显存"
                f"（{user_vram:g}GB），硬件资源不足以支撑方案运行。"
            )
            suggestion = (
                f"升级可用硬件配置至至少 {req_vram:g}GB 显存，"
                "或在复现方案中选用轻量化模型/减小 batch size。"
            )
        elif has_comparable_time and not time_feasible:
            basis = (
                f"复现方案预计耗时（{req_time:g} 小时）超出科研画像中的可用时间预算"
                f"（{user_time:g} 小时），时间可行性不足。"
            )
            suggestion = "在画像中增加可用时间周期，或在方案中优化实验规模与迭代轮数。"
        elif not has_comparable_hardware:
            basis = (
                "科研画像或方案中缺少可量化对照的显存规格（如 16GB/24GB），"
                "无法进行实际可行性比较。"
            )
            suggestion = (
                "在画像和复现方案中补充具体硬件显存规格（如单卡 RTX 3090 24GB 显存）。"
            )
        elif user_time is None and req_time is not None:
            basis = (
                "科研画像中缺少量化的时间周期预算（如 2周/1个月），"
                "无法核验方案的时间可行性。"
            )
            suggestion = "在科研画像中补充可用时间周期预算（如 2周或 1个月）。"
        elif req_time is None and user_time is not None:
            basis = (
                "复现方案中尚未记录方案运行的预计耗时（如 48小时/3天），"
                "无法对照用户时间预算核验时间可行性。"
            )
            suggestion = "在复现方案中明确方案运行所需的预计耗时与计算周期。"
        else:
            basis = (
                "科研画像与方案中均缺少量化的时间周期与预计耗时条件，"
                "无法进行时间可行性对照。"
            )
            suggestion = "在画像与方案中补充可用时间预算与实验预计耗时。"
    else:
        score = 0
        basis = "尚未记录计算资源、硬件环境或时间可行性约束。"
        suggestion = "在画像中补充算力设备与可用时间约束。"

    return (
        ReproductionEvaluationCriterion(
            criterion_no=5,
            title="计算资源与时间可行性",
            score=score,
            basis=basis,
            evidence_refs=evidence[:20],
        ),
        suggestion,
    )


_INTERVAL_PATTERNS = [
    re.compile(r"[\[\(]\s*\d+(?:\.\d+)?%?\s*[,~至到\-–]\s*\d+(?:\.\d+)?%?\s*[\]\)]"),
    re.compile(r"\b\d+(?:\.\d+)?%?\s*(?:~|至|到|\.{2,3}|to|\s+[-–]\s+)\s*\d+(?:\.\d+)?%?"),
    re.compile(r"\b\d+(?:\.\d+)?%?[-–]\d+(?:\.\d+)?%?"),
    re.compile(r"\b\d+(?:\.\d+)?%?\s*(?:±|\+\s*/\s*-|\+-\s*|\\pm)\s*\d+(?:\.\d+)?%?"),
]


def _has_strict_numerical_range(content: str) -> bool:
    return any(bool(pat.search(content)) for pat in _INTERVAL_PATTERNS)


def _has_numerical_metric_result(bundles: list[ExperimentEvidenceBundle]) -> bool:
    failure_keywords = ("失败", "中断", "异常", "oom", "error", "failed", "crash", "不足")
    for bundle in bundles:
        bundle_text = (
            f"{bundle.experiment_name.content} {bundle.goal.content} "
            + " ".join(item.content for item in bundle.items)
        )
        if any(kw in bundle_text.lower() for kw in ("oom", "error", "failed", "crash", "中断失败")):
            continue
        for item in bundle.items:
            if item.category in ("metric_or_result", "result_table"):
                if not any(kw in item.content.lower() for kw in failure_keywords):
                    if re.search(r"\d", item.content):
                        return True
    return False


def _criterion_results_verification(
    experiment_bundles: list[ExperimentEvidenceBundle],
    pipeline: ReproductionPipelineEvaluationView | None,
) -> tuple[ReproductionEvaluationCriterion, str | None]:
    has_baselines = bool(pipeline and pipeline.baseline_entries)
    has_expected_range = bool(
        pipeline
        and (
            any(_has_strict_numerical_range(e.content) for e in pipeline.baseline_entries)
            or any(_has_strict_numerical_range(e.content) for e in pipeline.objective_entries)
        )
    )
    has_numerical_results = _has_numerical_metric_result(experiment_bundles)

    evidence: list[ReproductionEvaluationEvidence] = []
    if pipeline:
        evidence.extend(_pipeline_evidence(pipeline.baseline_entries, pipeline.pipeline_id))
    if experiment_bundles:
        evidence.extend(
            ReproductionEvaluationEvidence(
                source_type="experiment_evidence",
                source_id=b.bundle_id,
                label=b.experiment_name.content,
                classification=b.experiment_name.classification,
                information_scope=_EXPERIMENT_SCOPE,
                basis=f"用户报告实验记录：{b.goal.content}",
            )
            for b in experiment_bundles[:10]
        )

    if has_baselines and has_expected_range and has_numerical_results:
        score = 2
        basis = "已保存结构化对照基线、明确预期数值区间及实际有效实验结果记录，具备对照核验路径。"
        suggestion = None
    elif has_baselines or has_expected_range or experiment_bundles:
        score = 1
        missing_elements = []
        if not has_baselines:
            missing_elements.append("结构化对照基线")
        if not has_expected_range:
            missing_elements.append("明确预期数值区间（如 [0.80, 0.85] 或 81.5% ± 0.5%）")
        if not has_numerical_results:
            missing_elements.append("非失败的数值实验结果证据（如 metric_or_result）")
        basis = f"已记录部分核验要素，但仍缺少{'、'.join(missing_elements)}，核验路径尚未完整建立。"
        suggestion = f"补充{'、'.join(missing_elements)}，以建立完整的基线对照与实验核验路径。"
    else:
        score = 0
        basis = "尚未保存对照基线、预期数值区间或实验结果记录，无法建立核验路径。"
        suggestion = "在复现方案中补充基线模型与预期数值区间，并提交实验运行结果记录。"

    return (
        ReproductionEvaluationCriterion(
            criterion_no=6,
            title="结果核验路径（baseline 与预期区间）",
            score=score,
            basis=basis,
            evidence_refs=evidence[:20],
        ),
        suggestion,
    )


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
