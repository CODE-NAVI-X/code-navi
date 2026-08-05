"""Rules-only experiment design suggestions for a ready research plan."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationResearchPlan,
    ExperimentDesign,
    ResearchPlanEntry,
    ResearchProfile,
)
from .research_artifact_llm import ResearchArtifactGenerator


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
    question = _bounded(
        next(iter(profile.research_questions or profile.candidate_questions), "研究问题"),
        700,
    )
    infer = _entry("inference")
    verify = _entry("to_verify")
    rules = ExperimentDesign(
        hypothesis=infer(
            f"建议检验：在定义的对照条件下，“{question}”可观察到差异。", f"研究问题：{question}"
        ),
        variables=[
            infer(
                "将方法/基线作为自变量，并预先固定数据切分和处理流程。",
                "规则研究计划的候选方法/基线。",
            ),
            verify(
                "因变量、混杂因素和成功阈值需由用户或导师确认。",
                "当前画像未提供经过验证的操作化定义。",
            ),
        ],
        data_sources=plan.suggested_datasets_or_metrics,
        baselines=plan.candidate_methods_or_baselines,
        metrics=[
            verify(
                "为每个研究问题选择一项主指标和一项失败/风险记录指标。",
                "当前没有可验证的指标或阈值。",
            )
        ],
        steps=plan.two_week_mvp_plan,
        resources=[
            verify(
                "样本量、设备、数据授权和伦理/隐私要求待确认。",
                "当前约束：" + ("；".join(profile.constraints) or "尚未明确"),
            )
        ],
        risks=[risk.risk for risk in plan.risks_and_mitigations],
        advisor_confirmation_items=[
            verify(
                "确认研究问题的可测性、基线公平性与主指标。",
                "这是导师确认项，不是系统已获批准的结论。",
            )
        ],
        provenance_note="实验方案只由已校验科研画像和规则研究计划离线生成；所有内容是建议或待验证项，不写文件、不安装依赖、不执行代码或实验。",
    )
    if generator is None:
        return rules
    if conversation_id is None:
        raise ValueError("conversation_id is required for model experiment design")
    outcome = generator.generate(
        kind="experiment_design",
        conversation_id=conversation_id,
        context={
            "profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json"),
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
                "research_hypothesis": "use hypothesis",
                "variables_and_controls": "use variables",
                "data_sources": "ResearchPlanEntry[]",
                "candidate_baselines": "use baselines",
                "metrics": "ResearchPlanEntry[]",
                "experiment_steps": "use steps",
                "two_week_mvp": "include within steps",
                "required_resources": "use resources",
                "risks_and_mitigations": "use risks",
                "advisor_confirmation_items": "ResearchPlanEntry[]",
                "provenance_note": "string",
                "actual_response_keys": [
                    "hypothesis", "variables", "data_sources", "baselines", "metrics",
                    "steps", "resources", "risks", "advisor_confirmation_items", "provenance_note",
                ],
            },
        },
    )
    if outcome.status == "unavailable":
        return rules
    if outcome.status != "generated" or outcome.text is None:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})
    try:
        return ExperimentDesign.model_validate_json(outcome.text).model_copy(
            update={
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
            }
        )
    except ValueError:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})


def _entry(classification: str):
    def make(content: str, basis: str) -> ResearchPlanEntry:
        return ResearchPlanEntry(content=content, classification=classification, basis=basis)

    return make


def _bounded(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"
