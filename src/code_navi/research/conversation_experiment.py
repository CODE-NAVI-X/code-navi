"""LLM-authored experiment design suggestions for a ready research plan."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationResearchPlan,
    ExperimentDesign,
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
                "risks": "string[]",
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
