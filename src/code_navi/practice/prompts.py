"""Prompts for P1-A code-fill generation, static grading and symbol explanation."""

from __future__ import annotations

CODE_FILL_SYSTEM_PROMPT = (
    "你是 Python 动手实践出题助手。先给出一段完整、可运行且不依赖真实外部数据的代码，"
    "然后从代码中裁剪 2~6 处核心逻辑作为填空。不得挖空 import、变量名、常量或琐碎语法；"
    "每处填空必须有唯一稳定 blank_id、答案和不超过 3 个等价写法。"
    "代码超过 200 行或涉及多文件/框架工程结构时，"
    "complexity 必须为 heavy 且 judge_mode 为 explain_only；"
    "否则 complexity 为 light 且 judge_mode 为 llm_static。"
    "同时输出 1~5 个 step，每个 step 说明 title、reason 和 sub_steps。"
    "只输出 JSON 对象，不要 Markdown，结构为："
    '{"items":[{"title":"...","complexity":"light|heavy","judge_mode":"llm_static|explain_only",'
    '"reference_code":"...","code_masked":"...",'
    '"blanks":[{"blank_id":"...","answer":"...","alternate_answers":["..."],"hint":"...","step_no":1}],'
    '"steps":[{"step_no":1,"title":"...","reason":"...","sub_steps":["..."]}]}]}'
)

CODE_FILL_STATIC_GRADER_SYSTEM_PROMPT = (
    "你是代码填空静态判题助手。只做静态正确性/等价性分析，禁止声称执行过代码。"
    "服务端规则已经判定完全匹配的空白；你只负责未命中空白。"
    "对每个未命中空白给出 correct、score(0 或 max_score)、comment，并说明是否接受等价写法。"
    "只输出 JSON 对象，不要 Markdown，结构为："
    '{"results":[{"blank_id":"...","correct":false,"score":0,"comment":"..."}]}'
)

EXPLAIN_SYMBOL_SYSTEM_PROMPT = (
    "你是代码符号解析助手。只根据用户提供的 name、kind 和 code_excerpt 解释该符号的功能，"
    "不得断言摘录之外的调用方、执行结果或项目结构。输出不超过 600 字的中文解释，"
    "只输出 JSON 对象：{'explanation':'...'}。"
)

PROJECT_EXPLAIN_SYSTEM_PROMPT = (
    "你是项目代码讲解助手。只能根据用户提供的文件文本和符号结构解释，不执行代码，不推断运行结果。"
    "每条结论必须分入 fact（文本直接可见）、inference（基于命名或调用关系的推测）"
    "或 to_verify（需要用户确认的信息）。"
    "只输出 JSON：{\"entries\":[{\"path\":\"...\",\"symbol\":null,\"fact\":[\"...\"],"
    "\"inference\":[\"...\"],\"to_verify\":[\"...\"]}]}。"
)


def code_fill_user_prompt(topic: str, count: int, difficulty: str) -> str:
    """Build the user prompt for one code-fill generation request."""
    return (
        f"请围绕知识点「{topic}」生成 {count} 个 Python code_fill 练习，难度为 {difficulty}。"
        "代码必须完整可运行，但填空只保留核心逻辑。"
    )


def static_grade_user_prompt(
    reference_code: str,
    blanks: list[dict],
    answers: list[dict],
) -> str:
    """Build the user prompt for static grading unmatched blanks."""
    import json

    return json.dumps(
        {
            "reference_code": reference_code,
            "blanks": blanks,
            "student_answers": answers,
        },
        ensure_ascii=False,
    )


def explain_symbol_user_prompt(name: str, kind: str, code_excerpt: str) -> str:
    """Build the user prompt for one hover-symbol explanation."""
    import json

    return json.dumps(
        {
            "name": name,
            "kind": kind,
            "code_excerpt": code_excerpt,
        },
        ensure_ascii=False,
    )


def project_explain_user_prompt(project_name: str, files: list[dict[str, str]]) -> str:
    """Build a bounded project explanation request without execution claims."""
    import json

    return json.dumps({"project_name": project_name, "files": files}, ensure_ascii=False)
