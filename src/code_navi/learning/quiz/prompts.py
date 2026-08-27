"""Prompt templates for the learning quiz generator.

This is a Chinese-language port of OpenMAIC's ``quiz-content`` prompt pair
(``lib/prompts/templates/quiz-content/{system,user}.md``) with three changes:

- a new ``fill_blank`` question type (OpenMAIC only had single/multiple/short_answer);
- LaTeX math is **enabled** — OpenMAIC explicitly asked for plain text; here the
  stem / option labels may embed ``$...$`` math, which the docx exporter renders
  as native Word equations;
- ``answer`` is normalized to a ``string[]`` in all cases, matching the shared
  grading helpers (``lib/quiz/grading.ts``).
"""

# ruff: noqa: E501 -- prompt text; wrapping instruction lines changes the prompt.

from __future__ import annotations

from .schemas import Difficulty, QuestionType

_SECTION_LABELS = {
    "single": "单项选择题",
    "fill_blank": "填空题",
    "short_answer": "解答题",
}


def _type_hints(types: list[QuestionType]) -> str:
    """Render per-type JSON shapes shown to the model."""
    blocks: list[str] = []
    for t in types:
        label = _SECTION_LABELS[t]
        if t == "single":
            blocks.append(
                f"""### {label} ({t})

只选一个正确选项。选项 label 可含 $...$ LaTeX 数学公式。

{{"id": "q1", "type": "single", "question": "题干，可含 $...$ 数学公式", "options": [{{"label": "选项A内容", "value": "A"}}, {{"label": "选项B内容", "value": "B"}}, {{"label": "选项C内容", "value": "C"}}, {{"label": "选项D内容", "value": "D"}}], "answer": ["A"], "analysis": "解析", "points": 10}}"""
            )
        elif t == "fill_blank":
            blocks.append(
                f"""### {label} ({t})

题干中用 ______（6 个下划线）标出每一个待填空位，answer 数组按空位顺序给出每空答案，
答案可以是数字、表达式或含 $...$ 的 LaTeX 公式。空位数 = answer 数组长度。

{{"id": "q2", "type": "fill_blank", "question": "题干 ______ 题干继续 ______", "answer": ["3", "x > 1"], "analysis": "解析", "points": 10}}"""
            )
        else:
            blocks.append(
                f"""### {label} ({t})

开放型解答题，需书写完整过程。给出 commentPrompt 评分要点与 analysis 参考答案。

{{"id": "q3", "type": "short_answer", "question": "题干，可含 $...$ 数学公式", "commentPrompt": "评分要点：(1) 步骤A - 40% (2) 步骤B - 30% (3) 表达规范 - 30%", "analysis": "参考答案或关键步骤", "points": 20}}"""
            )
    return "\n\n".join(blocks)


QUIZ_SYSTEM_PROMPT = """\
你是一位专业的教育试题命题专家。请根据给定的知识点，生成一组练习题，输出一个 JSON 数组。

## 通用要求

- 每题必须包含 `id`、`type`、`question`、`analysis`（解析/参考答案）、`points`（分值）、`source`（来源）。
- 题干与选项内容可以嵌入 $...$ 表示的 LaTeX 数学公式（如 $\\frac{1}{2}$、$x^2$、$\\sqrt{2}$）。
- 题目必须清晰无歧义，聚焦给定知识点；选项要有干扰性但不含"以上都对/都错"。
- 不要编造事实；难度与指定难度匹配。

{extra_rules}

## 题型定义

{type_blocks}

## 设计原则

- 单选题的正确答案位置要随机分布，不要总是第一个。
- 填空每题 1~2 个空；解答题需有详细评分要点。
- 难度：easy=基础记忆与直接应用；medium=需要理解与简单分析；hard=需要综合运用或复杂推理。

## 来源标注要求（NON-NEGOTIABLE）

- 每题必须携带 `source` 对象：`{"type": "generated"|"web"|"local_bank", "label": "来源描述", "uri": "https://..."}`。
- 纯生成题目：`source.type="generated"`，`label="AI 生成"`。
- 基于网络素材改编：`source.type="web"`，`label="改编自 <网站或标题>"`，`uri` 填素材原文 URL；**必须引用用户提供的素材，禁止编造 URL**。
- 找不到对应素材时不得标注 web 来源。

## 输出格式（NON-NEGOTIABLE）

直接输出一个 JSON 数组，不要任何其他文字、不要 markdown 代码块包裹：

[
  {
    "id": "q1",
    "type": "single",
    "question": "题干",
    "options": [
      {"label": "选项A内容", "value": "A"},
      {"label": "选项B内容", "value": "B"},
      {"label": "选项C内容", "value": "C"},
      {"label": "选项D内容", "value": "D"}
    ],
    "answer": ["A"],
    "analysis": "解析",
    "points": 10,
    "source": {"type": "generated", "label": "AI 生成", "uri": null}
  }
]

- 数组长度必须严格等于要求的题目数量。
- 只允许出现要求的题型，不要输出其他类型。
"""


def _student_profile_note(profile: str | None) -> str:
    """Render the 学情 adaptation block when a profile is provided."""
    if not profile or not profile.strip():
        return ""
    return (
        "## 学情适配（重要）\n"
        "以下是该学生的学情上下文。请据此调整每道题的难度与内容，让题目"
        "适合该生水平：\n"
        f"{profile.strip()[:2000]}\n"
        "- 难度可以略高于其当前水平以形成挑战，但不应超出其理解范围。\n"
        "- 内容应覆盖其薄弱点，避免在其已熟练掌握处重复出题。\n\n"
    )


def _web_material_note(material: str | None) -> str:
    """Render the retrieved web material block used as adaptation source."""
    if not material or not material.strip():
        return ""
    return (
        "## 网络检索素材（改编依据）\n"
        "以下是从网上检索到的素材。请**优先据此改编**题目（不得照抄原文，"
        "应重写为原创题目），并在每题 source 中标明改编来源与 URL：\n"
        f"{material.strip()[:4000]}\n\n"
    )


def build_quiz_system_prompt(
    question_types: list[QuestionType],
    *,
    student_profile: str | None = None,
    web_material: str | None = None,
) -> str:
    """Render the system prompt with the requested type shapes + dynamic blocks."""
    extra = _student_profile_note(student_profile) + _web_material_note(web_material)
    return QUIZ_SYSTEM_PROMPT.replace("{type_blocks}", _type_hints(question_types)).replace(
        "{extra_rules}", extra
    )


def quiz_user_prompt(
    knowledge_point: str,
    question_count: int,
    question_types: list[QuestionType],
    difficulty: Difficulty,
    with_latex: bool,
) -> str:
    """Build the user turn for quiz generation."""
    latex_note = (
        "数学公式请用 $...$ 包裹的 LaTeX 表达。"
        if with_latex
        else "本题目不使用 LaTeX，公式一律用中文/Unicode 纯文本描述。"
    )
    types_text = "、".join(_SECTION_LABELS[t] for t in question_types)
    return (
        f"知识点：{knowledge_point}\n"
        f"题目数量：{question_count}\n"
        f"题型：{types_text}\n"
        f"难度：{difficulty}\n"
        f"公式要求：{latex_note}\n"
        "请输出该知识点的练习题 JSON 数组。"
    )


AUDIT_SYSTEM_PROMPT = """\
你是一位严谨的试卷审核专家。请对一组已生成的练习题进行审核，输出一个 JSON 对象。

## 审核维度

1. difficulty_fit（难度匹配度，0~10）：题目难度是否与该生的学情（如有）及指定难度匹配。
2. coverage（知识点覆盖，0~10）：题目是否聚焦并覆盖给定知识点的核心内容，是否偏题。
3. quality（质量，0~10）：题干是否无歧义、选项是否合理、答案与解析是否正确、有无重复题。

## 输出格式（NON-NEGOTIABLE）

直接输出 JSON 对象，不要其他文字、不要代码块：

{
  "verdict": "pass" | "adjust",
  "scores": [
    {"dimension": "difficulty_fit", "score": 8, "note": "一句话理由"},
    {"dimension": "coverage", "score": 8, "note": "一句话理由"},
    {"dimension": "quality", "score": 8, "note": "一句话理由"}
  ],
  "notes": ["可执行的具体修改建议1", "建议2"]
}

- verdict=adjust 当且仅当有必须修改的问题（错误、严重偏题、难度严重不匹配）。
- notes 给 0~4 条具体、可执行的意见；无问题时为空数组。
"""

REVISE_SYSTEM_PROMPT = """\
你是一位专业的教育试题命题专家。上一轮生成的一组题目未通过审核，请你根据审核意见修订后重新输出。

## 要求

- 逐条落实审核意见（改错、调难度、补覆盖、删重复），未涉及的问题不要无谓改动。
- 保持题目数量、题型、总体结构不变。
- 沿用原题 id；新增/替换题目用新 id。
- 每题仍须包含 `id`、`type`、`question`、`analysis`、`points`、`source` 字段，字段含义与输出格式同初版生成约定。

## 输出格式（NON-NEGOTIABLE）

直接输出 JSON 对象，不要其他文字、不要代码块：

{
  "summary": "一句话说明本轮修订了哪些内容",
  "questions": [ ...原题格式的 JSON 数组... ]
}
"""


def audit_user_prompt(
    questions_json: str,
    knowledge_point: str,
    difficulty: Difficulty,
    student_profile: str | None,
) -> str:
    """Build the user turn for the post-generation audit."""
    profile = student_profile or "（未提供）"
    return (
        f"知识点：{knowledge_point}\n"
        f"目标难度：{difficulty}\n"
        f"学情：{profile[:800]}\n"
        "待审核题目：\n"
        f"{questions_json[:12000]}"
    )


def revise_user_prompt(audit_notes: list[str], questions_json: str) -> str:
    """Build the user turn for the revision round."""
    notes = "\n".join(f"- {n}" for n in audit_notes) or "- （无）"
    return f"审核意见：\n{notes}\n\n待修订题目：\n{questions_json[:12000]}"


GRADE_SYSTEM_PROMPT = """\
你是一位严谨、公正的教育评卷专家。请根据标准答案与评分要点，对学生的作答逐题评分，输出一个 JSON 数组。

## 评分规则

- 每题输出一个对象：{"question_id": "...", "score": <0 到满分之间的整数>, "comment": "<中文评分解析>"}。
- score 必须在 0 到该题满分之间；未作答直接给 0。
- 填空题：逐空比对，正确空数 / 总空数折算，可给部分分；与参考答案等价但写法不同的正确表达一律算对
  （如 $x > 1$ 与 x>1、x \\gt 1 视为相同；同义改写、不同但等价的推导结果算对）。
- 解答题：按评分要点（comment_prompt）分步给分，重视思路与过程，不只看最终结果；写清得分理由与扣分点。
- comment 用中文简明写出：得分理由、扣分点、以及改进建议。不要输出其他字段。

## 输出格式（NON-NEGOTIABLE）

直接输出 JSON 数组，不要任何其他文字、不要 markdown 代码块：

[
  {"question_id": "q2", "score": 10, "comment": "……"},
  {"question_id": "q3", "score": 15, "comment": "……"}
]
"""


def grade_user_prompt(questions_json: str, answers_json: str) -> str:
    """Build the user turn for LLM grading of fill_blank / short_answer."""
    return (
        "以下是要批改的题目（含题干、满分、标准答案、解析与评分要点）：\n"
        f"{questions_json[:12000]}\n\n"
        "学生作答：\n"
        f"{answers_json[:8000]}\n\n"
        "请按评分规则逐题给出分数与中文评语，输出 JSON 数组。"
    )


__all__ = [
    "QUIZ_SYSTEM_PROMPT",
    "AUDIT_SYSTEM_PROMPT",
    "REVISE_SYSTEM_PROMPT",
    "GRADE_SYSTEM_PROMPT",
    "build_quiz_system_prompt",
    "quiz_user_prompt",
    "audit_user_prompt",
    "revise_user_prompt",
    "grade_user_prompt",
    "_SECTION_LABELS",
]
