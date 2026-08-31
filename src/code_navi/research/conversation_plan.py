"""Deterministic research-plan suggestions for the conversational workflow."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationResearchPlan,
    ResearchPlanEntry,
    ResearchPlanRisk,
    ResearchProfile,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import (
    ResearchGenerationError,
    require_contract_fields,
    require_generated_artifact,
)


def build_conversation_research_plan(
    profile: ResearchProfile,
    *,
    ready_for_plan: bool,
) -> ConversationResearchPlan | None:
    """Build suggestions from profile values without inferring external facts."""
    if not ready_for_plan:
        return None

    question = next(iter(profile.research_questions or profile.candidate_questions), None)
    methods = _method_entries(profile)
    data_and_metrics = _data_and_metric_entries(profile)
    pending = _pending_entries(profile, question)
    return ConversationResearchPlan(
        research_title=_title_entry(profile, question),
        research_goal=_goal_entry(profile, question),
        candidate_methods_or_baselines=methods,
        suggested_datasets_or_metrics=data_and_metrics,
        two_week_mvp_plan=_mvp_entries(profile, question),
        risks_and_mitigations=_risk_entries(profile),
        suggested_search_keywords=_search_keywords(profile, question),
        pending_items=pending,
        provenance_note=(
            "本计划仅由用户已确认的科研画像按规则整理，不访问模型、论文或网络。"
            "其中所有条目都是推断建议或待验证项，不构成论文事实、实验结论或已验证的方法。"
        ),
    )


def build_llm_research_plan(
    profile: ResearchProfile,
    *,
    generator: ResearchArtifactGenerator | None,
    conversation_id: str,
    ready_for_plan: bool = True,
) -> ConversationResearchPlan | None:
    """Generate a user-visible plan through the shared audited LLM boundary."""
    if not ready_for_plan:
        return None
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "research_plan: generator is unavailable"
        )
    deterministic_context = build_conversation_research_plan(
        profile, ready_for_plan=True
    )
    if deterministic_context is None:
        return None
    outcome = generator.generate(
        kind="research_plan",
        conversation_id=conversation_id,
        context={
            "profile": profile.model_dump(mode="json"),
            "planning_hints": deterministic_context.model_dump(mode="json"),
            "source_boundary": {
                "allowed_classifications": ["inference", "to_verify"],
                "forbidden": [
                    "不得新增 fact 分类。",
                    "不得把画像之外的实验结果、数据划分、超参数或资源写成事实。",
                    "不得访问网络、论文全文或执行代码。",
                ],
            },
            "required_json_shape": {
                "research_title": "ResearchPlanEntry",
                "research_goal": "ResearchPlanEntry",
                "candidate_methods_or_baselines": "ResearchPlanEntry[]",
                "suggested_datasets_or_metrics": "ResearchPlanEntry[]",
                "two_week_mvp_plan": "ResearchPlanEntry[]",
                "risks_and_mitigations": "ResearchPlanRisk[]",
                "suggested_search_keywords": "string[]",
                "pending_items": "ResearchPlanEntry[]",
                "core_judgment": "string",
                "next_action": "string",
                "provenance_note": "string",
            },
        },
    )
    try:
        plan = ConversationResearchPlan.model_validate_json(
            require_generated_artifact(outcome, kind="research_plan")
        )
        entries = [
            plan.research_title,
            plan.research_goal,
            *plan.candidate_methods_or_baselines,
            *plan.suggested_datasets_or_metrics,
            *plan.two_week_mvp_plan,
            *plan.pending_items,
            *(item.risk for item in plan.risks_and_mitigations),
            *(item.mitigation for item in plan.risks_and_mitigations),
        ]
        if any(item.classification not in {"inference", "to_verify"} for item in entries):
            raise ValueError("research plan contains an unsupported classification")
        require_contract_fields(
            {
                "core_judgment": plan.core_judgment,
                "next_action": plan.next_action,
            },
            kind="research_plan",
        )
        for plan_entry in entries:
            require_contract_fields(
                {
                    "relevance": plan_entry.relevance,
                    "suggested_action": plan_entry.suggested_action,
                },
                kind="research_plan entry",
            )
        return plan.model_copy(
            update={
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
                "provenance_note": (
                    "本研究计划由模型基于已确认科研画像生成；规则仅校验结构、准入和事实边界。"
                    "所有条目均为建议或待验证项，不构成论文事实或实验结论。"
                ),
            }
        )
    except ResearchGenerationError:
        raise
    except ValueError as error:
        raise ResearchGenerationError(
            "invalid_output", "research_plan: boundary validation failed"
        ) from error


def _inference(content: str, basis: str) -> ResearchPlanEntry:
    return ResearchPlanEntry(
        content=_bounded(content), classification="inference", basis=_bounded(basis)
    )


def _to_verify(content: str, basis: str) -> ResearchPlanEntry:
    return ResearchPlanEntry(
        content=_bounded(content), classification="to_verify", basis=_bounded(basis)
    )


def _bounded(value: str, limit: int = 900) -> str:
    """Keep user-provided profile text within the public response contract."""
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _title_entry(profile: ResearchProfile, question: str | None) -> ResearchPlanEntry:
    if not profile.topic:
        return _to_verify(
            "研究主题尚待确认；先明确研究对象或现象，再形成可检索的题目。",
            f"当前研究问题：{question or '尚未明确'}",
        )
    if not question:
        return _to_verify(
            f"“{profile.topic}”的优先研究问题尚待确认，不能把主题直接当作题目。",
            f"用户已确认的研究主题：{profile.topic}",
        )
    return _inference(
        f"建议研究题目：{profile.topic}中关于{question}的最小可行验证",
        f"用户已确认的研究主题：{profile.topic}；当前研究问题：{question}",
    )


def _goal_entry(profile: ResearchProfile, question: str | None) -> ResearchPlanEntry:
    if not question:
        return _to_verify(
            "研究目标尚待确认；先选择一个要比较、解释或解决的优先问题。",
            f"当前研究主题：{profile.topic or '尚未明确'}",
        )
    return _inference(
        f"建议先界定“{question}”可被观察和比较的结果，再完成一轮最小验证。",
        f"当前研究问题：{question}",
    )


def _method_entries(profile: ResearchProfile) -> list[ResearchPlanEntry]:
    if profile.methods:
        return [
            _inference(
                f"建议将“{method}”作为候选方法路径，并预先定义可比较的基线或对照条件。",
                f"用户已提及的方法：{method}",
            )
            for method in profile.methods[:3]
        ]
    return [
        _to_verify(
            "尚未明确候选方法或基线；先确认可执行的比较路径后再选择。",
            "当前画像只具备主题、问题、场景或数据条件，未给出具体方法。",
        )
    ]


def _data_and_metric_entries(profile: ResearchProfile) -> list[ResearchPlanEntry]:
    entries: list[ResearchPlanEntry] = []
    if profile.data_requirements:
        entries.append(
            _inference(
                f"建议先核验“{profile.data_requirements}”是否足以支持当前研究问题。",
                f"用户说明的数据或材料条件：{profile.data_requirements}",
            )
        )
    else:
        entries.append(
            _to_verify(
                "数据集、样本或材料范围尚待确认，不能预设可用数据。",
                "当前科研画像没有明确数据需求。",
            )
        )
    entries.append(
        _to_verify(
            "在实施前定义与研究问题匹配的评测指标、对照条件和成功阈值。",
            "当前画像未提供已经验证的指标或实验结论。",
        )
    )
    return entries


def _mvp_entries(profile: ResearchProfile, question: str | None) -> list[ResearchPlanEntry]:
    constraint = "；".join(profile.constraints[:2]) or "当前资源与时间条件"
    first_step = (
        _inference(
            f"第 1–3 天：把“{question}”改写为可观察的输入、比较对象与输出。",
            f"研究问题：{question}",
        )
        if question
        else _to_verify(
            "第 1–3 天：先确认一个优先研究问题，再定义可观察的输入、比较对象与输出。",
            "当前科研画像没有已确认的研究问题。",
        )
    )
    return [
        first_step,
        _inference(
            "第 4–8 天：整理可获得材料，完成一条最小方法或基线的可重复试跑。",
            f"数据条件：{profile.data_requirements or '尚待确认'}",
        ),
        _inference(
            "第 9–14 天：记录结果、失败条件和限制，输出研究简报或原型复盘。",
            f"预期产出：{profile.expected_output or '尚待确认'}；约束：{constraint}",
        ),
    ]


def _risk_entries(profile: ResearchProfile) -> list[ResearchPlanRisk]:
    data_basis = profile.data_requirements or "数据条件尚未明确"
    constraints = "；".join(profile.constraints) or "尚未记录具体约束"
    return [
        ResearchPlanRisk(
            risk=_to_verify(
                "数据、样本或材料可能不足以支持比较；在未核验前不能宣称可执行。",
                data_basis,
            ),
            mitigation=_inference(
                "建议先做小样本或公开材料的可行性检查，并记录无法满足的条件。",
                data_basis,
            ),
        ),
        ResearchPlanRisk(
            risk=_to_verify(
                "当前时间、资源或范围限制可能使研究问题过大。",
                constraints,
            ),
            mitigation=_inference(
                "建议将两周目标限定为一个问题、一条方法路径和一项可复核产出。",
                constraints,
            ),
        ),
    ]


def _search_keywords(profile: ResearchProfile, question: str | None) -> list[str]:
    values = [
        profile.topic,
        question,
        profile.context,
        *profile.methods[:2],
        *profile.evidence_preferences[:2],
    ]
    return list(dict.fromkeys(_bounded(value, 300) for value in values if value))[:8]


def _pending_entries(
    profile: ResearchProfile,
    question: str | None,
) -> list[ResearchPlanEntry]:
    pending = [
        _to_verify(uncertainty, "当前科研画像明确记录为不确定项。")
        for uncertainty in profile.uncertainties[:5]
    ]
    if not question:
        pending.append(
            _to_verify(
                "需要由用户确认一个优先研究问题，不能把候选问题当作最终结论。",
                "当前只有主题或候选方向。",
            )
        )
    if not profile.expected_output:
        pending.append(
            _to_verify(
                "预期交付物尚待确认，应在实施前明确是简报、原型还是其他可复核产出。",
                "当前科研画像没有明确预期产出。",
            )
        )
    return pending


__all__ = ["build_conversation_research_plan", "build_llm_research_plan"]
