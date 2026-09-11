"""CNN 固定**提问**流程（``CNN_FLOW``）。

与 ``cnn_preset.py``（演示预设）的边界：

- 本模块只固定**入口、提问顺序、每个问题的目的、状态机、确认门控、红线规则**；
- 研究方向、数据集、模型、输入尺寸、计算资源、测试样本、随机种子、训练轮数、
  解释方法、指标、实验规模与最终论文，**必须由用户逐项输入并确认**；
- 系统建议在用户明确确认前一律标记为“系统建议，尚未确认”，不得写入 confirmed 条件；
- 演示预设（固定答案/固定论文）只能通过 ``我想研究CNN演示`` 进入，
  普通 ``我想研究CNN`` 入口不得使用演示候选。

状态持久化：``state_model.subtasks["cnn_flow"]``（现有 JSON 字段，不新增数据库字段）：

``{"phase": ..., "answers": {field: {"raw","value","confirmed","suggested"}}, ...}``
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .cnn_preset import (
    CNN_REPLY_BLOCK_REPRODUCTION,
    is_cnn_preset_trigger,
    is_reproduction_success_claim,
)

#: 普通入口触发（末尾句号归一化后完全相等）。
CNN_FLOW_TRIGGER_TEXT = "我想研究CNN"
#: 隔离的演示路径触发（与普通入口互斥）。
CNN_FLOW_DEMO_TRIGGER_TEXT = "我想研究CNN演示"

CNN_FLOW_FALLBACK = "当前正在执行 CNN 研究流程。\n\n请按照当前步骤完成确认，不要跳过论文确认。"

#: (字段, 问题文本, 是否允许“请推荐”)。顺序即产品契约。
CNN_FLOW_QUESTIONS: tuple[tuple[str, str, bool], ...] = (
    (
        "direction",
        "你想研究 CNN 的哪一个方面？\n\n"
        "你可以直接输入自己的想法，也可以选择：\n\n"
        "A. 用 CNN 完成一个具体任务\n"
        "B. 改进 CNN 的结构或训练方法\n"
        "C. 研究数据增强对 CNN 的影响\n"
        "D. 研究 CNN 的可解释性\n"
        "E. 还没有想好",
        False,
    ),
    ("dataset", "问题 2：你准备使用什么数据集？\n如果还没有确定，可以说“还没有”。", True),
    ("model", "问题 3：你准备使用什么 CNN 模型？\n如果还没有确定，可以说“请推荐”。", True),
    ("input_size", "问题 4：你的输入图像尺寸是多少？\n如果不知道，可以说“不确定”。", False),
    (
        "compute",
        "问题 5：你目前有什么计算资源？\n"
        "请说明 GPU 型号和显存；如果没有 GPU，也请直接说明。",
        False,
    ),
    ("test_samples", "问题 6：你计划使用多少张测试样本？\n如果还没有决定，可以说“请推荐”。", True),
    ("random_seeds", "问题 7：你希望使用几个随机种子？\n可以输入数量，也可以让系统推荐。", True),
    ("epochs", "问题 8：每组实验计划训练多少轮？\n如果还没有决定，可以说“请推荐”。", True),
    (
        "explanation_method",
        "问题 9：你希望使用什么解释方法？\n如果还没有决定，可以说“请推荐”。",
        True,
    ),
    (
        "metrics",
        "问题 10：你准备用什么指标衡量解释稳定性？\n如果还没有决定，可以说“请推荐”。",
        True,
    ),
    ("scale", "问题 11：你希望先做小规模验证，还是直接进行完整实验？", False),
)

CNN_FLOW_FIELD_LABELS: dict[str, str] = {
    "direction": "研究方向",
    "dataset": "数据集",
    "model": "模型",
    "input_size": "输入尺寸",
    "compute": "计算资源",
    "test_samples": "测试样本",
    "random_seeds": "随机种子",
    "epochs": "训练轮数",
    "explanation_method": "解释方法",
    "metrics": "稳定性指标",
    "scale": "实验规模",
}

#: 系统建议（只在用户说“请推荐”时给出，且**未确认前不得写入 confirmed 条件**）。
CNN_FLOW_SUGGESTIONS: dict[str, str] = {
    "direction": (
        "可以先从一个具体的 CNN 任务、结构或训练方法、数据增强影响，"
        "或模型可解释性问题开始"
    ),
    "dataset": "CIFAR-10",
    "model": "ResNet-18",
    "test_samples": "64 张",
    "random_seeds": "0、1、2",
    "epochs": "20 epoch",
    "explanation_method": "GradientSHAP",
    "metrics": "Spearman 相关系数、Top-10 特征重合率",
    "scale": "先小规模验证，再决定是否扩大实验",
}

#: 用户表示“没有值”的整句（必须是整句相等，不能子串匹配——
#: 「还没有 GPU」是真实回答，不是未确定）。
_NO_VALUE_PHRASES = frozenset(
    {
        "还没有",
        "还没定",
        "还没决定",
        "没有决定",
        "不确定",
        "不知道",
        "没想过",
        "没有想好",
        "暂无",
        "无",
        "没有",
    }
)

_RECOMMEND_PHRASES = frozenset(
    {"请推荐", "推荐", "让系统推荐", "系统推荐", "请你推荐", "你推荐", "帮我推荐"}
)

#: 用户确认系统建议的表述。
_ADOPTION_MARKERS = ("确认", "采用", "同意", "可以", "好的", "没问题", "行", "就这样")

#: 汇总确认表述。
_SUMMARY_CONFIRM_MARKERS = ("确认", "准确", "没问题", "对", "同意", "正确", "是的", "好的")

# 否定或疑问表述不能被上面的子串标记误判为确认/采纳。
_NEGATED_CONFIRMATION_MARKERS = (
    "不确认",
    "不同意",
    "不准确",
    "不对",
    "不采用",
    "不采纳",
    "不接受",
    "不认为",
    "不想",
    "不可以",
    "不要",
    "不行",
    "不选择",
    "不设置",
    "不设为",
    "不要这篇",
    "换一篇",
    "暂不",
    "尚未",
    "还没",
)

#: 中文研究用语 → supplemental English query 术语（只翻译用户已确认的内容）。
_EN_TERM_MAP: tuple[tuple[str, str], ...] = (
    ("数据增强", "data augmentation"),
    ("解释稳定性", "explanation stability"),
    ("归因稳定性", "attribution stability"),
    ("特征归因", "feature attribution"),
    ("可解释性", "interpretability explainability"),
    ("图像分类", "image classification"),
    ("随机种子", "random seeds"),
    ("输入尺寸", "input size"),
    ("测试样本", "test samples"),
    ("训练轮数", "training epochs"),
    ("相关系数", "rank correlation"),
    ("重合率", "overlap"),
    ("小规模验证", "small-scale validation"),
    ("消融", "ablation"),
)

# 只剥离回答开头的界面选项前缀；正文中的 ``Ablation``、``A/B testing`` 等
# 真实术语不能被改写。用户原始回答仍保存在 answers[field]["raw"] 中。
_DISPLAY_OPTION_PREFIX_PATTERN = re.compile(
    r"^\s*(?:(?:我\s*)?(?:选|选择)\s*)?[A-Ga-g](?:\s*[.．、:：)）-]\s*|\s+)"
)


def _normalize_trigger(message: str) -> str:
    text = (message or "").strip()
    while text and text[-1] in "。.":
        text = text[:-1].rstrip()
    return text


def is_cnn_flow_trigger(message: str) -> bool:
    """是否为普通 CNN 固定提问流程入口（完整匹配）。"""
    return _normalize_trigger(message) == CNN_FLOW_TRIGGER_TEXT


def is_cnn_flow_demo_trigger(message: str) -> bool:
    """是否为隔离的演示路径入口（复用演示预设的触发判定，避免字面量漂移）。"""
    return is_cnn_preset_trigger(message)


def _is_no_value(text: str) -> bool:
    return text.strip() in _NO_VALUE_PHRASES


def _wants_recommendation(text: str) -> bool:
    return text.strip() in _RECOMMEND_PHRASES


def _clean_query_value(value: object) -> str:
    return _DISPLAY_OPTION_PREFIX_PATTERN.sub("", str(value or "").strip(), count=1).strip()


def _is_negated_or_question(text: str) -> bool:
    """Reject negative or interrogative text before substring confirmation checks."""
    normalized = (text or "").strip()
    if any(marker in normalized for marker in _NEGATED_CONFIRMATION_MARKERS):
        return True
    return normalized.startswith(("是否", "能否", "可否")) or normalized.endswith(
        ("吗", "么", "？", "?")
    )


def classify_answer(field: str, message: str) -> str:
    """把当前回答分类为 ``no_value`` / ``recommend`` / ``answer``。"""
    text = (message or "").strip()
    if not text:
        return "answer"
    if _is_no_value(text):
        return "no_value"
    if _wants_recommendation(text):
        return "recommend"
    return "answer"


def cnn_flow_reply_intro() -> str:
    """入口回复：不得写死任何实验条件，且一次只问第一个问题。"""
    first_field, first_question, _ = CNN_FLOW_QUESTIONS[0]
    return (
        "我知道了，你想围绕 CNN 开展研究。\n\n"
        "我会先逐步确认你的研究方向、数据条件和实验资源，"
        "不会直接替你假设实验参数。\n\n"
        "我们先从研究目标开始。\n\n"
        f"{first_question}"
    )


def cnn_flow_question_reply(field: str) -> str:
    """单个问题的提问文本。"""
    for question_field, question, _ in CNN_FLOW_QUESTIONS:
        if question_field == field:
            return question
    raise KeyError(field)


def cnn_flow_recorded_reply(field: str, value: str | None) -> str:
    """确认用户刚给出的回答（逐字复述，不增删用户没有说过的内容）。"""
    label = CNN_FLOW_FIELD_LABELS[field]
    shown = value if value else "未确定"
    return f"已记录你的{label}：\n\n{shown}"


def cnn_flow_suggestion_reply(field: str) -> str:
    """给出系统建议，并明确“尚未确认”。"""
    suggestion = CNN_FLOW_SUGGESTIONS[field]
    return f"系统建议：{suggestion}\n该建议尚未确认。是否采用这个方案？"


def cnn_flow_summary(answers: Mapping[str, Mapping[str, object]]) -> str:
    """根据用户真实回答生成汇总；未确认/缺失的一律显示“未确定”。"""
    lines: list[str] = []
    for field, _question, _allow in CNN_FLOW_QUESTIONS:
        label = CNN_FLOW_FIELD_LABELS[field]
        entry = answers.get(field) or {}
        if entry.get("confirmed") and entry.get("value"):
            lines.append(f"{label}：{entry['value']}")
        elif entry.get("confirmed") is False and entry.get("suggested"):
            lines.append(f"{label}：系统建议，尚未确认（{entry.get('value') or '未确定'}）")
        else:
            lines.append(f"{label}：未确定")
    return (
        "以下是本次研究条件的汇总（只包含你已输入或明确确认的内容）：\n\n"
        + "\n".join(lines)
        + "\n\n以上内容是否准确？"
    )


def cnn_flow_confirmed_values(answers: Mapping[str, Mapping[str, object]]) -> dict[str, str]:
    """只取用户已确认的值；未确认/缺失字段不出现在结果里。"""
    values: dict[str, str] = {}
    for field, _question, _allow in CNN_FLOW_QUESTIONS:
        entry = answers.get(field) or {}
        if entry.get("confirmed") and entry.get("value"):
            values[field] = str(entry["value"])
    return values


def build_cnn_flow_queries(answers: Mapping[str, Mapping[str, object]]) -> dict[str, str] | None:
    """构造检索 query。

    - ``query_zh``：用户原始中文回答（逐字保留，不翻译、不改写）；
    - ``query_en``：supplemental English query（只翻译用户已确认的中文术语，
      保留拉丁/数字术语原样）。
    - 没有已确认的研究方向时返回 ``None``（不得伪造 query，也不得用无关默认词）。
    """
    confirmed = cnn_flow_confirmed_values(answers)
    direction = confirmed.get("direction")
    if not direction:
        return None

    ordered_values = [
        _clean_query_value(confirmed[field])
        for field, _question, _allow in CNN_FLOW_QUESTIONS
        if field in confirmed
    ]
    query_zh = " ".join(dict.fromkeys(value for value in ordered_values if value))

    en_text = _clean_query_value(direction)
    for field in ("dataset", "model", "input_size", "explanation_method", "metrics"):
        value = confirmed.get(field)
        if value:
            en_text = f"{en_text} {_clean_query_value(value)}"
    for source_term, en_term in _EN_TERM_MAP:
        en_text = en_text.replace(source_term, f" {en_term} ")
    # supplemental query 只保留拉丁/数字术语；未翻译的中文术语不丢——
    # 它们完整保留在 query_zh（原始中文研究描述）里，两者分开保存。
    cjk = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
    en_tokens = " ".join(
        dict.fromkeys(
            token
            for token in (part.strip("，、；;,.") for part in en_text.split())
            if token and not cjk.search(token)
        )
    )
    return {"query_zh": query_zh, "query_en": en_tokens}


def cnn_flow_stage_four_reply(answers: Mapping[str, Mapping[str, object]]) -> str:
    """第四阶段内容：只显示用户已确认的条件，缺失的一律“未确定”。"""
    confirmed = cnn_flow_confirmed_values(answers)
    lines = []
    for field, _question, _allow in CNN_FLOW_QUESTIONS:
        if field == "direction":
            continue
        label = CNN_FLOW_FIELD_LABELS[field]
        lines.append(f"- {label}：{confirmed.get(field, '未确定')}")
    return (
        "第四阶段已开启。\n\n"
        "本次分析任务（只包含你已明确确认的实验条件；未提供的字段一律显示“未确定”，"
        "不会替你假设）：\n\n"
        + "\n".join(lines)
        + "\n\n注意：实验尚未执行，以上只是已确认的实验计划，不代表实验结果。"
    )


def cnn_flow_next_field(answers: Mapping[str, Mapping[str, object]]) -> str | None:
    """下一个尚未回答的问题字段；全部回答完返回 ``None``。"""
    for field, _question, _allow in CNN_FLOW_QUESTIONS:
        if field not in answers:
            return field
    return None


def cnn_flow_matches_step(phase: str, message: str) -> bool:
    """用户输入是否与当前流程步骤匹配（宽松但确定性）。"""
    text = (message or "").strip()
    if not text:
        return False
    if phase == "await_select":
        return any(
            key in text
            for key in ("选择", "候选", "第1篇", "第 1 篇", "第一篇", "精读")
        )
    if phase == "await_confirm":
        return "确认" in text and not _is_negated_or_question(text)
    if phase == "await_analysis":
        return "分析" in text or "第四阶段" in text
    return False


def cnn_flow_summary_confirmed(message: str) -> bool:
    """用户是否明确确认了汇总。"""
    text = (message or "").strip()
    return not _is_negated_or_question(text) and any(
        marker in text for marker in _SUMMARY_CONFIRM_MARKERS
    )


def cnn_flow_suggestion_adopted(message: str) -> bool:
    """用户是否明确采用了系统建议。"""
    text = (message or "").strip()
    return not _is_negated_or_question(text) and any(
        marker in text for marker in _ADOPTION_MARKERS
    )


def cnn_flow_suggestion_rejected(message: str) -> bool:
    """Whether the user explicitly rejected or questioned a suggestion."""
    return _is_negated_or_question(message)


def cnn_flow_redline_reply(message: str) -> str | None:
    """复现成功红线（与演示路径共用同一套识别词与契约文案）。"""
    if is_reproduction_success_claim(message):
        return CNN_REPLY_BLOCK_REPRODUCTION
    return None


def cnn_flow_field_update(message: str) -> tuple[str, str] | None:
    """用户在汇总阶段指出某字段需要修改时，解析 ``字段 + 内容``。"""
    text = (message or "").strip()
    for field, label in CNN_FLOW_FIELD_LABELS.items():
        marker = f"{label}："
        if marker in text:
            value = text.split(marker, 1)[1].strip()
            return field, value
    return None


__all__ = [
    "CNN_FLOW_DEMO_TRIGGER_TEXT",
    "CNN_FLOW_FALLBACK",
    "CNN_FLOW_FIELD_LABELS",
    "CNN_FLOW_QUESTIONS",
    "CNN_FLOW_SUGGESTIONS",
    "CNN_FLOW_TRIGGER_TEXT",
    "build_cnn_flow_queries",
    "cnn_flow_confirmed_values",
    "cnn_flow_field_update",
    "cnn_flow_matches_step",
    "cnn_flow_next_field",
    "cnn_flow_question_reply",
    "cnn_flow_recorded_reply",
    "cnn_flow_redline_reply",
    "cnn_flow_stage_four_reply",
    "cnn_flow_suggestion_reply",
    "cnn_flow_summary",
    "cnn_flow_summary_confirmed",
    "cnn_flow_suggestion_adopted",
    "cnn_flow_suggestion_rejected",
    "classify_answer",
    "is_cnn_flow_demo_trigger",
    "is_cnn_flow_trigger",
]
