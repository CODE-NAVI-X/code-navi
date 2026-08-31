"""LLM-authored experiment design suggestions for a ready research plan."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationResearchPlan,
    ExperimentDesign,
    PaperAnalysis,
    ResearchProfile,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact

_EXPERIMENT_PROVENANCE = (
    "实验方案由模型基于已校验科研画像和规则研究计划生成；所有内容是建议或待验证项，"
    "不写文件、不安装依赖、不执行代码或实验。无法确认的内容标记为 to_verify。"
)


def build_experiment_design(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    paper_analysis: PaperAnalysis | None = None,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
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
    outcome = generator.generate(
        kind="experiment_design",
        conversation_id=conversation_id,
        context={
            "profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json"),
            "selected_paper_analysis": (
                paper_analysis.model_dump(mode="json") if paper_analysis else None
            ),
            "writing_guidance": [
                "方案必须围绕当前科研画像、研究计划以及 selected_paper_analysis（如有）展开，"
                "不要输出脱离本研究对象的通用实验清单。",
                "每个条目的 content 用 2 至 4 句说明目的、具体做法、可观察产出或判定标准；"
                "步骤要写清前置条件、操作顺序和需要记录的结果。",
                "对模型结构、数据划分、超参数、指标阈值和资源条件，只有上下文或论文证据明确覆盖时才可具体陈述；"
                "其余内容必须标记为 to_verify，并说明需要核对的来源。",
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
                "hypothesis": "ResearchPlanEntry",
                "variables": "ResearchPlanEntry[]",
                "data_sources": "ResearchPlanEntry[]",
                "baselines": "ResearchPlanEntry[]",
                "metrics": "ResearchPlanEntry[]",
                "steps": "ResearchPlanEntry[]",
                "resources": "ResearchPlanEntry[]",
                "risks": "ResearchPlanEntry[]",
                "advisor_confirmation_items": "ResearchPlanEntry[]",
                "provenance_note": "string",
            },
        },
    )
    try:
        design = ExperimentDesign.model_validate_json(
            require_generated_artifact(outcome, kind="experiment_design")
        )
        _assert_experiment_boundary(design)
        return design.model_copy(
            update={
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
                "provenance_note": _EXPERIMENT_PROVENANCE,
            }
        )
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
