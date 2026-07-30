"""Deterministic rules for the five-field research-clarification workflow."""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import ClarificationQuestion, ResearchBrief, ResearchState


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


def build_brief(state: ResearchState) -> ResearchBrief | None:
    """Return a brief only after every required rule field is available."""
    if not is_complete(state):
        return None
    return ResearchBrief(**state.model_dump())
