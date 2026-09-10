"""从姜姜的澄清回复中提取结构化的「待答问题 + 建议答案」。

背景：前端此前只能从 Markdown 正文里碰巧写出的 ``A. `` / ``B. `` 解析出可点击选项，
而真实模型常返回「1. … 2. …」这种编号建议，于是页面上没有任何按钮。

这里把「识别候选答案」收敛成后端的一次性、可测试的纯逻辑，并把它写成
``next_question`` / ``suggested_answers`` 结构化字段随消息一起持久化。
前端只消费结构化字段，不再依赖正文的书写形式。

提取规则刻意保守，宁可没有选项也不伪造选项：

1. 候选答案必须是**紧跟在某一行问句之后**的连续列表项（允许中间空行），
   中间夹了任何一句别的正文就判定为「不是这题的候选」；
2. 列表项数量必须落在 ``[MIN_OPTIONS, MAX_OPTIONS]``（2~4）之内，
   因此普通编号执行步骤（如 5 条计划）不会被误判成选择题；
3. 列表项本身不能长成一段正文，过长即整体放弃；
4. 一个都没匹配上时只返回问题（或 ``None``），``suggested_answers`` 留空，
   前端据此保持自由输入。
"""

from __future__ import annotations

import re

#: 少于 2 项不成组：单选没有意义。
MIN_OPTIONS = 2
#: 多于 4 项就不是「建议答案」，而是正文里的编号步骤。
MAX_OPTIONS = 4
#: 单项过长说明这是段落而不是可点选的答案。
MAX_OPTION_LENGTH = 150

#: 列表项标记：``- `` / ``1.`` / ``1、`` / ``（1）`` / ``A.`` / ``A：`` 等。
_LIST_MARKER = re.compile(
    r"^(?:"
    r"(?P<bullet>[-*•·+])\s+"
    r"|(?P<number>\d{1,2})\s*[.、)）]\s*"
    r"|[(（]\s*(?P<paren>\d{1,2})\s*[)）]\s*"
    r"|(?P<letter>[A-Ga-g])\s*[.、)：:]\s*"
    r")"
)


def _clean_inline(text: str) -> str:
    """去掉行内 Markdown 装饰（``#`` 标题、``**`` 强调），保留可展示的原文。"""
    cleaned = text.strip()
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "")
    return cleaned.strip()


def _is_question_line(line: str) -> bool:
    """问句判定：以 ``？``/``?`` 结尾，且本身不是一个列表项。"""
    stripped = line.strip()
    if not stripped or _LIST_MARKER.match(stripped):
        return False
    core = _clean_inline(stripped)
    return core.endswith("？") or core.endswith("?")


def _option_text(line: str) -> str | None:
    """把一行列表项转成可展示的候选答案；不是列表项则返回 ``None``。"""
    stripped = line.strip()
    marker = _LIST_MARKER.match(stripped)
    if marker is None:
        return None
    rest = stripped[marker.end():]
    # ``3.14`` 这类小数／版本号不是列表项
    if not rest or rest[0].isdigit():
        return None
    text = _clean_inline(rest)
    if not text or len(text) > MAX_OPTION_LENGTH:
        return None
    return text


def _collect_options_after(lines: list[str], start: int) -> list[str]:
    """收集 ``start`` 之后紧邻的连续列表项（允许中间空行）。"""
    options: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            # 空行不打断列表，但也不能无限穿透到下一段正文
            continue
        text = _option_text(line)
        if text is None:
            break
        options.append(text)
    return options


def extract_clarification_options(
    text: str,
    *,
    min_options: int = MIN_OPTIONS,
    max_options: int = MAX_OPTIONS,
) -> tuple[str | None, list[str]]:
    """返回 ``(next_question, suggested_answers)``。

    - 找到「问句 + 紧邻的 2~4 条候选」时，两者一并返回；
    - 只找到问句时，返回该问句与空列表（前端保持自由输入）；
    - 都没有时返回 ``(None, [])``。
    """
    if not text or not text.strip():
        return None, []

    lines = text.split("\n")

    for index, line in enumerate(lines):
        if not _is_question_line(line):
            continue
        options = _collect_options_after(lines, index + 1)
        if min_options <= len(options) <= max_options:
            return _clean_inline(line), options

    # 没有可点选的候选项：仍把最后一道问句留作「待答问题」，但不伪造选项。
    last_question = next(
        (_clean_inline(line) for line in reversed(lines) if _is_question_line(line)),
        None,
    )
    return last_question, []
