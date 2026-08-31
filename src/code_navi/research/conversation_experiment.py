"""LLM-authored experiment design suggestions for a ready research plan."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationResearchPlan,
    DatasetRef,
    ExperimentDesign,
    MetricSpec,
    PaperAnalysis,
    ResearchPlanEntry,
    ResearchProfile,
)
from .metrics_catalog import (
    STANDARD_METRICS,
    TaskType,
    find_standard_metric,
    infer_task_type,
    strip_numeric_assertion,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact

_EXPERIMENT_PROVENANCE = (
    "实验方案由模型基于已校验科研画像和规则研究计划生成；所有内容是建议或待验证项，"
    "不写文件、不安装依赖、不执行代码或实验。无法确认的内容标记为 to_verify。"
)


def _reduce_metric_specs(
    raw_metric_specs: list[dict[str, object]] | list[MetricSpec] | None,
    legacy_metrics: list[ResearchPlanEntry] | None,
    current_task_type: TaskType,
) -> list[MetricSpec]:
    """Reduce and normalize metric specs according to metrics_catalog (§2.4)."""
    reduced: list[MetricSpec] = []

    candidates: list[dict[str, object]] = []
    if raw_metric_specs:
        for spec in raw_metric_specs:
            if isinstance(spec, MetricSpec):
                candidates.append(spec.model_dump(mode="json"))
            elif isinstance(spec, dict):
                candidates.append(spec)
    elif legacy_metrics:
        for entry in legacy_metrics:
            content = entry.content
            parts = content.split("：", 1) if "：" in content else content.split(":", 1)
            name = parts[0].strip()[:64]
            definition = parts[1].strip() if len(parts) > 1 else content.strip()
            candidates.append(
                {
                    "name": name,
                    "definition": definition[:300],
                    "formula": None,
                    "higher_is_better": True,
                    "applies_to_task_type": [current_task_type],
                    "source": "model_suggested",
                    "to_verify": True,
                }
            )

    for cand in candidates[:10]:
        raw_name = str(cand.get("name") or "").strip()[:64]
        raw_definition = str(cand.get("definition") or "").strip()[:300]
        raw_formula = str(cand.get("formula") or "").strip()[:300] if cand.get("formula") else None
        higher_is_better = bool(cand.get("higher_is_better", True))
        applies_to = cand.get("applies_to_task_type")
        valid_tasks = (
            "classification",
            "regression",
            "clustering",
            "retrieval",
            "generation",
            "other",
        )
        if not isinstance(applies_to, list) or not applies_to:
            applies_to = [current_task_type]
        else:
            filtered = [str(t) for t in applies_to if t in valid_tasks]
            applies_to = filtered or [current_task_type]

        standard_def = find_standard_metric(raw_name)
        if standard_def is not None:
            # Name hit standard catalog -> source=standard_catalog, backfill definition & formula
            reduced.append(
                MetricSpec(
                    name=standard_def.name,
                    definition=standard_def.definition[:300],
                    formula=standard_def.formula[:300] if standard_def.formula else None,
                    higher_is_better=standard_def.higher_is_better,
                    applies_to_task_type=standard_def.applies_to_task_type,
                    source="standard_catalog",
                    to_verify=False,
                )
            )
        else:
            # Not in catalog -> source=model_suggested, to_verify=True, strip numeric assertion
            cleaned_def = strip_numeric_assertion(raw_definition)[:300]
            reduced.append(
                MetricSpec(
                    name=raw_name,
                    definition=cleaned_def or "待验证的模型建议指标",
                    formula=raw_formula,
                    higher_is_better=higher_is_better,
                    applies_to_task_type=applies_to,
                    source="model_suggested",
                    to_verify=True,
                )
            )

    return reduced


def _reduce_dataset_refs(
    raw_dataset_refs: list[dict[str, object]] | list[DatasetRef] | None,
    legacy_data_sources: list[ResearchPlanEntry] | None,
) -> list[DatasetRef]:
    """Reduce and normalize dataset refs according to contract (§2.4)."""
    reduced: list[DatasetRef] = []

    candidates: list[dict[str, object]] = []
    if raw_dataset_refs:
        for ref in raw_dataset_refs:
            if isinstance(ref, DatasetRef):
                candidates.append(ref.model_dump(mode="json"))
            elif isinstance(ref, dict):
                candidates.append(ref)
    elif legacy_data_sources:
        for entry in legacy_data_sources:
            candidates.append(
                {
                    "name": entry.content[:200],
                    "url": None,
                    "license_note": None,
                    "to_verify": True,
                }
            )

    for cand in candidates[:10]:
        name = str(cand.get("name") or "").strip()[:200]
        url = cand.get("url")
        raw_url = str(url).strip()[:2000] if url and str(url).strip() else None
        # Publicly accessible URL check (starts with http:// or https://)
        is_accessible_url = raw_url is not None and (
            raw_url.startswith("http://") or raw_url.startswith("https://")
        )
        license_note = cand.get("license_note")
        raw_license = (
            str(license_note).strip()[:200]
            if license_note and str(license_note).strip()
            else None
        )

        # If no publicly accessible URL, to_verify=True
        to_verify = bool(cand.get("to_verify", False)) or not is_accessible_url

        reduced.append(
            DatasetRef(
                name=name or "未命名数据集",
                url=raw_url if is_accessible_url else None,
                license_note=raw_license,
                to_verify=to_verify,
            )
        )

    return reduced


def _project_legacy_metrics(specs: list[MetricSpec]) -> list[ResearchPlanEntry]:
    """Project MetricSpec items to legacy metrics ResearchPlanEntry for backward compatibility."""
    entries: list[ResearchPlanEntry] = []
    for spec in specs:
        content = f"{spec.name}：{spec.definition}"[:1000]
        classification = "to_verify" if spec.to_verify else "inference"
        basis = "标准指标目录" if spec.source == "standard_catalog" else "模型建议指标（待核验）"
        entries.append(
            ResearchPlanEntry(
                content=content,
                classification=classification,
                basis=basis[:1000],
                relevance=f"评估 {spec.name} 指标以验证方案效果"[:1000],
                suggested_action=f"核验 {spec.name} 计算脚本与评估协议"[:1000],
            )
        )
    return entries


def _project_legacy_data_sources(refs: list[DatasetRef]) -> list[ResearchPlanEntry]:
    """Project DatasetRef items to legacy data_sources ResearchPlanEntry for compatibility."""
    entries: list[ResearchPlanEntry] = []
    for ref in refs:
        content = f"{ref.name} ({ref.url})"[:1000] if ref.url else ref.name[:1000]
        classification = "to_verify" if ref.to_verify else "inference"
        basis = (
            f"公开可访问数据源：{ref.url}"[:1000]
            if ref.url
            else "无公开URL数据源，需核验数据可用性"
        )
        entries.append(
            ResearchPlanEntry(
                content=content,
                classification=classification,
                basis=basis[:1000],
                relevance="用于实验模型训练或基准评估"[:1000],
                suggested_action="核验数据集公开下载地址及许可证说明"[:1000],
            )
        )
    return entries


def build_experiment_design(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    paper_analysis: PaperAnalysis | None = None,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
    task_type_override: TaskType | None = None,
) -> ExperimentDesign | None:
    """Return no design before a plan; never claim unprovided resources are available."""
    if plan is None:
        return None
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "experiment_design: generator is unavailable"
        )
    if conversation_id is None:
        raise ValueError("conversation_id is required for model experiment design")

    # Determine task_type: user override takes precedence over rule-based inference
    inferred = infer_task_type(
        methods=profile.methods,
        research_questions=profile.research_questions,
        topic=profile.topic,
    )
    task_type: TaskType = task_type_override or inferred

    # Build metric catalog whitelist text for the current task_type (§2.7)
    catalog_metrics_for_task = [
        f"- {m.name}: {m.definition} (公式: {m.formula or '无'})"
        for m in STANDARD_METRICS
        if task_type in m.applies_to_task_type
    ]
    catalog_whitelist_doc = (
        f"任务类型 [{task_type}] 的标准指标目录白名单：\n"
        + "\n".join(catalog_metrics_for_task)
        if catalog_metrics_for_task
        else f"任务类型 [{task_type}] 无固定标准指标，建议使用各领域权威通用指标并标明待核验。"
    )

    outcome = generator.generate(
        kind="experiment_design",
        conversation_id=conversation_id,
        context={
            "profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json"),
            "task_type": task_type,
            "selected_paper_analysis": (
                paper_analysis.model_dump(mode="json") if paper_analysis else None
            ),
            "writing_guidance": [
                f"当前实验方案任务类型已确立为 [{task_type}]。",
                "方案必须围绕当前科研画像、研究计划以及 selected_paper_analysis（如有）展开，"
                "不要输出脱离本研究对象的通用实验清单。",
                "每个条目的 content 用 2 至 4 句说明目的、具体做法、可观察产出或判定标准；"
                "步骤要写清前置条件、操作顺序和需要记录的结果。",
                "【指标规范白名单要求】：请优先选用标准指标目录中的指标。"
                "严禁编造「准确率 92%」等臆测数值断言。\n"
                f"{catalog_whitelist_doc}",
                "【数据源规范要求】：建议的数据源必须提供公开可访问的 URL（http:// 或 https://）；"
                "无公开 URL 的数据源必须将 to_verify 设为 true。",
                "优先给出可在当前设备和时间范围内执行的最小对照设计，同时解释它如何回答研究问题，"
                "不要把建议写成已经完成的实验或论文结论。",
                "每个 ResearchPlanEntry 必须同时返回 content、classification 和 basis；"
                "basis 要明确说明该建议来自科研画像、研究计划或已提供的论文分析哪一部分。",
            ],
            "detail_requirements": {
                "hypothesis": (
                    "明确自变量、因变量、比较对象和可观察的预期差异；"
                    "不写未经实验验证的结果。"
                ),
                "variables": (
                    "给出每个变量的 operational definition、控制方式、记录字段"
                    "和可能的混杂因素。"
                ),
                "data_sources": "说明数据用途、划分或预处理需要核对的内容，以及对应的来源边界。",
                "baselines": "说明为什么能与主方法比较、保持哪些条件一致，以及比较输出。",
                "metrics": "说明指标定义、统计方式、成功阈值来源；没有来源时标记 to_verify。",
                "steps": "按前置条件、操作、产出和记录项展开，形成可复核的执行顺序。",
                "resources_and_risks": (
                    "说明资源限制如何影响方案，并给出可观察的风险信号"
                    "和应对动作。"
                ),
                "paper_mismatch": (
                    "若选中论文与当前研究问题不完全匹配，明确指出相关性风险，"
                    "不把它当作复现依据。"
                ),
            },
            "source_boundary": {
                "allowed_classifications": ["inference", "to_verify"],
                "forbidden": [
                    "不得声称数据、样本、GPU、许可或资源已经可用。",
                    "不得把建议写成已验证的实验结论。",
                    "不得自造指标数值断言（如准确率达到90%）。",
                ],
            },
            "hard_limits": {
                "variables": 6,
                "data_sources": 4,
                "baselines": 4,
                "metrics": 4,
                "steps": 6,
                "resources": 4,
                "risks": 4,
                "advisor_confirmation_items": 4,
                "classification": "inference|to_verify",
            },
            "required_json_shape": {
                "task_type": task_type,
                "hypothesis": "ResearchPlanEntry",
                "variables": "ResearchPlanEntry[]",
                "metric_specs": [
                    {
                        "name": "string",
                        "definition": "string",
                        "formula": "string|null",
                        "higher_is_better": "boolean",
                        "applies_to_task_type": ["string"],
                        "source": "standard_catalog|model_suggested",
                        "to_verify": "boolean",
                    }
                ],
                "dataset_refs": [
                    {
                        "name": "string",
                        "url": "string|null (必须为公开可访问 URL)",
                        "license_note": "string|null",
                        "to_verify": "boolean",
                    }
                ],
                "baselines": "ResearchPlanEntry[]",
                "steps": "ResearchPlanEntry[]",
                "resources": "ResearchPlanEntry[]",
                "risks": "ResearchPlanEntry[]",
                "advisor_confirmation_items": "ResearchPlanEntry[]",
                "provenance_note": "string",
            },
        },
    )
    try:
        raw_text = require_generated_artifact(outcome, kind="experiment_design")
        design = ExperimentDesign.model_validate_json(raw_text)

        # Reducer: normalize metric_specs and dataset_refs (§2.4)
        reduced_metric_specs = _reduce_metric_specs(
            design.metric_specs,
            legacy_metrics=design.metrics,
            current_task_type=task_type,
        )
        reduced_dataset_refs = _reduce_dataset_refs(
            design.dataset_refs,
            legacy_data_sources=design.data_sources,
        )

        # Project backward-compatible legacy fields if empty or needed
        projected_metrics = (
            _project_legacy_metrics(reduced_metric_specs)
            if reduced_metric_specs
            else design.metrics
        )
        projected_data_sources = (
            _project_legacy_data_sources(reduced_dataset_refs)
            if reduced_dataset_refs
            else design.data_sources
        )

        # Check for unverified metrics/datasets to reflect in provenance_note
        has_unverified_metrics = any(spec.to_verify for spec in reduced_metric_specs)
        has_unverified_datasets = any(ref.to_verify for ref in reduced_dataset_refs)
        provenance_additions = []
        if has_unverified_metrics:
            provenance_additions.append("部分未命中标准目录指标已降级为待核验建议并剥离数值断言")
        if has_unverified_datasets:
            provenance_additions.append("无公开可访问URL的数据源已标注为待核验")

        provenance_note = _EXPERIMENT_PROVENANCE
        if provenance_additions:
            provenance_note += f"；{'，'.join(provenance_additions)}。"

        updated_design = design.model_copy(
            update={
                "task_type": task_type,
                "metric_specs": reduced_metric_specs,
                "dataset_refs": reduced_dataset_refs,
                "metrics": projected_metrics,
                "data_sources": projected_data_sources,
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
                "provenance_note": provenance_note,
            }
        )
        _assert_experiment_boundary(updated_design)
        return updated_design
    except ResearchGenerationError:
        raise
    except ValueError as error:
        raise ResearchGenerationError(
            "invalid_output", "experiment_design: boundary validation failed"
        ) from error


def _assert_experiment_boundary(design: ExperimentDesign) -> None:
    entries = [
        design.hypothesis,
        *design.variables,
        *design.data_sources,
        *design.baselines,
        *design.metrics,
        *design.steps,
        *design.resources,
        *design.advisor_confirmation_items,
    ]
    if any(item.classification == "fact" for item in entries):
        raise ValueError("model cannot introduce fact-classified experiment guidance")
