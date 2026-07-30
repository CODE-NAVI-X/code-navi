"""Deterministic rules for the five-field research-clarification workflow."""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import (
    ClarificationQuestion,
    ResearchBrief,
    ResearchPlan,
    ResearchPlanEntry,
    ResearchPlanRisk,
    ResearchState,
)


@dataclass(frozen=True)
class FieldRule:
    key: str
    label: str
    question: str
    options: tuple[str, str, str]


FIELD_RULES = (
    FieldRule(
        "research_domain",
        "研究领域",
        "你的研究主要属于哪个领域？",
        ("人工智能与机器学习", "软件工程与系统", "网络与信息安全"),
    ),
    FieldRule(
        "core_question",
        "核心问题",
        "你希望重点解决或验证什么问题？",
        ("提升准确性或效果", "比较方法或基线", "分析机制或影响因素"),
    ),
    FieldRule(
        "data_and_method",
        "数据与方法",
        "你计划使用什么数据、对象或研究方法？",
        ("公开数据集与实验评测", "问卷/访谈等实证研究", "原型系统与案例分析"),
    ),
    FieldRule(
        "constraints",
        "约束条件",
        "有哪些时间、资源、数据或合规限制？",
        ("两周内完成最小验证", "仅使用公开数据与开源工具", "需要满足课程或竞赛要求"),
    ),
    FieldRule(
        "expected_deliverable",
        "预期交付物",
        "你最终希望产出什么？",
        ("可复现的实验报告", "原型系统与演示", "调研综述与研究计划"),
    ),
)


def missing_fields(state: ResearchState) -> list[str]:
    """Return missing field keys in their fixed collection order."""
    return [rule.key for rule in FIELD_RULES if not getattr(state, rule.key)]


def is_complete(state: ResearchState) -> bool:
    """Completion is controlled by the five fixed rules, never by a model."""
    return not missing_fields(state)


def next_question(state: ResearchState) -> ClarificationQuestion | None:
    """Return the next deterministic prompt, or none after completion."""
    missing = missing_fields(state)
    if not missing:
        return None
    rule = next(rule for rule in FIELD_RULES if rule.key == missing[0])
    return ClarificationQuestion(
        field=rule.key,
        label=rule.label,
        question=rule.question,
        options=list(rule.options),
    )


def is_recommendation_request(value: str) -> bool:
    """Recognize uncertainty requests that must not be persisted as field values."""
    normalized = value.replace(" ", "").lower()
    return any(
        marker in normalized
        for marker in ("不知道", "不清楚", "帮我推荐", "有什么推荐", "推荐一下")
    )


def rules_reply(question: ClarificationQuestion | None) -> str:
    """Return a deterministic reply when no validated model guidance is available."""
    if question is None:
        return "五项科研需求已经完整记录，已生成结构化研究简报和规则研究计划。"
    return f"请继续补充“{question.label}”，也可以从下面三个规则推荐项中选择。"


def build_brief(state: ResearchState) -> ResearchBrief | None:
    """Return a brief only after every required rule field is available."""
    if not is_complete(state):
        return None
    return ResearchBrief(**state.model_dump())


def _inference(content: str, basis: str) -> ResearchPlanEntry:
    """Create an explicitly non-factual recommendation derived from user input."""
    return ResearchPlanEntry(content=content, classification="inference", basis=basis)


def _to_verify(content: str, basis: str) -> ResearchPlanEntry:
    """Create an explicit unknown rather than filling it with an invented fact."""
    return ResearchPlanEntry(content=content, classification="to_verify", basis=basis)


def build_research_plan(state: ResearchState) -> ResearchPlan | None:
    """Return a deterministic, clearly labelled plan only after clarification completes."""
    brief = build_brief(state)
    if brief is None:
        return None

    domain_basis = f"用户澄清的研究领域：{brief.research_domain}"
    question_basis = f"用户澄清的核心问题：{brief.core_question}"
    method_basis = f"用户澄清的数据与方法：{brief.data_and_method}"
    constraint_basis = f"用户澄清的约束条件：{brief.constraints}"
    deliverable_basis = f"用户澄清的预期交付物：{brief.expected_deliverable}"

    return ResearchPlan(
        research_title=_inference(
            f"建议研究题目：{brief.research_domain}中关于{brief.core_question}的最小验证",
            f"{domain_basis}；{question_basis}",
        ),
        research_goal=_inference(
            f"建议围绕“{brief.core_question}”完成可复现的最小验证，并产出“{brief.expected_deliverable}”。",
            f"{question_basis}；{deliverable_basis}",
        ),
        candidate_methods_or_baselines=[
            _inference(
                f"建议以“{brief.data_and_method}”作为首个实施路径，并保留一个可复现的简单基线。",
                method_basis,
            ),
            _to_verify(
                "待确认：基线的具体名称、实现来源和适用前提需要通过后续受限学术检索核验。",
                "当前规则模式没有访问论文、数据集或代码来源。",
            ),
        ],
        suggested_datasets_or_metrics=[
            _to_verify(
                f"待确认：可用数据集或研究对象是否支持“{brief.data_and_method}”，并具备合适的使用许可。",
                method_basis,
            ),
            _inference(
                f"建议选择一个能直接检验“{brief.core_question}”的主指标，并在报告中说明其局限。",
                question_basis,
            ),
        ],
        two_week_mvp_plan=[
            _inference("第 1–2 天：细化研究问题、成功标准与最小对照方案。", question_basis),
            _inference(
                "第 3–5 天：确认数据/对象可得性，搭建可重复运行的最小实验或调研流程。",
                method_basis,
            ),
            _inference("第 6–10 天：执行最小验证，记录配置、异常和中间结果。", constraint_basis),
            _inference(
                "第 11–14 天：整理结果、限制与待验证项，形成预期交付物。",
                deliverable_basis,
            ),
        ],
        risks_and_mitigations=[
            ResearchPlanRisk(
                risk=_inference(
                    f"风险：在“{brief.constraints}”下，范围可能超过两周内可验证的最小工作量。",
                    constraint_basis,
                ),
                mitigation=_inference(
                    "建议：优先保留一个研究问题、一个实施路径和一个主指标，其余内容列为后续工作。",
                    constraint_basis,
                ),
            ),
            ResearchPlanRisk(
                risk=_to_verify(
                    "风险：数据、工具或评价标准的可得性与合规性尚未核验。",
                    method_basis,
                ),
                mitigation=_to_verify(
                    "建议：在实施前确认来源、许可、样本范围和可复现条件；无法确认时缩小目标。",
                    "当前规则模式未访问外部来源。",
                ),
            ),
        ],
        suggested_search_keywords=[
            brief.research_domain,
            brief.core_question,
            brief.data_and_method,
            f"{brief.research_domain} {brief.core_question}",
        ],
        provenance_note=(
            "本计划由固定规则根据用户完成的五字段研究简报生成；所有条目均为推断建议或待验证项，"
            "未调用模型、网络或论文来源，不能视为已验证事实。"
        ),
    )
