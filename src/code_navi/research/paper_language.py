"""候选论文标题的语言判定（纯逻辑，零依赖）。

浏览器事实（2026-09-11）：一次被误触发的检索把 4 篇与主题完全无关的中文论文
直接贴到了“检索候选论文卡片”上——

- 慢性乙型肝炎防治指南（2022年版）
- HUVEC 成管实验和结果分析
- 新型冠状病毒肺炎防控方案解读
- APTox：化学混合物毒性预测

用户的研究主题是 CIFAR-10 / ResNet / SHAP / 数据增强 / 解释稳定性，这些题录
既不相关也不是英文论文。此前 OpenAlex / Crossref 返回什么就展示什么，没有任何
语言过滤，于是中文题录直接进了候选卡片。

这里的判定刻意**保守**：宁可过滤掉可疑标题，也不把中文题录当英文候选展示。

1. 标题必须含拉丁字母，否则无法确认是英文标题 → 过滤（"1234"、"2024" 也算无法确认）；
2. 标题中的中日文字符占比超过 ``CJK_RATIO_LIMIT`` → 视为中文/中文为主的混合标题 → 过滤；
3. **不看来源名称**：arXiv / OpenAlex / Crossref 都不等于英文论文，
   arXiv 返回的中文题录同样要过滤。
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, TypeVar

#: 中文字符占「中文字符 + 拉丁字母」的比例上限；超过即认为不是英文标题。
CJK_RATIO_LIMIT = 0.2

#: 中日文表意文字与假名。
_CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
#: 拉丁字母。
_LATIN_PATTERN = re.compile(r"[A-Za-z]")

T = TypeVar("T")


def is_english_title(title: str) -> bool:
    """该标题是否可以**保守确认**为英文标题。"""
    text = (title or "").strip()
    if not text:
        return False
    if not _LATIN_PATTERN.search(text):
        # 没有拉丁字母（纯中文、纯数字、纯符号）都无法确认是英文标题。
        return False
    cjk_count = len(_CJK_PATTERN.findall(text))
    if cjk_count == 0:
        return True
    latin_count = len(_LATIN_PATTERN.findall(text))
    total = cjk_count + latin_count
    if total == 0:
        return False
    return (cjk_count / total) <= CJK_RATIO_LIMIT


def filter_english_titles(papers: Iterable[T]) -> list[T]:
    """按原顺序保留标题可保守确认英文的条目；不改写条目的任何字段。

    只读取 ``title``：不重排、不按来源过滤、不改写 source status / provenance，
    因此过滤后为空就是**如实为空**，绝不用无关论文补位。
    """
    kept: list[T] = []
    for paper in papers or []:
        if isinstance(paper, Mapping):
            title = paper.get("title")
        else:
            title = getattr(paper, "title", None)
        if is_english_title(str(title or "")):
            kept.append(paper)
    return kept


__all__ = ["CJK_RATIO_LIMIT", "filter_english_titles", "is_english_title"]
