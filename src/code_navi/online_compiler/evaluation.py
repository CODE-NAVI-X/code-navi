"""Deterministic execution classification and validated AI feedback models."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .piston import ExecutionResult

_SYNTAX_ERRORS = ("SyntaxError", "IndentationError", "TabError")
_EXCEPTION_PATTERN = re.compile(
    r"(?m)^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):\s*(?P<message>.*)$"
)
_LINE_PATTERN = re.compile(r'File "[^"]*main\.py", line (?P<line>\d+)')


@dataclass(frozen=True, slots=True)
class RuleAssessment:
    """A deterministic interpretation of one sandbox execution."""

    category: str
    severity: str
    title: str
    summary: str
    error_type: str | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize the assessment for the browser and learning record."""

        return {
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "errorType": self.error_type,
            "line": self.line,
            "source": "deterministic_rule",
        }


@dataclass(frozen=True, slots=True)
class QualityRubric:
    """AI-provided code quality reference dimensions."""

    readability: int
    structure: int
    robustness: int

    def __post_init__(self) -> None:
        for name in ("readability", "structure", "robustness"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
                raise ValueError(f"{name} must be an integer from 0 to 100")

    @property
    def overall(self) -> int:
        """Return the rounded mean reference score."""

        return round((self.readability + self.structure + self.robustness) / 3)

    def as_dict(self) -> dict[str, int]:
        """Serialize rubric dimensions and derived overall score."""

        return {
            "readability": self.readability,
            "structure": self.structure,
            "robustness": self.robustness,
            "overall": self.overall,
        }


@dataclass(frozen=True, slots=True)
class AiFeedback:
    """Validated model feedback that cannot replace the rule assessment."""

    explanation: str
    suggestions: tuple[str, ...]
    quality: QualityRubric

    def __post_init__(self) -> None:
        if not self.explanation.strip():
            raise ValueError("explanation must not be empty")
        if not 1 <= len(self.suggestions) <= 5:
            raise ValueError("suggestions must contain one to five items")
        if any(not item.strip() for item in self.suggestions):
            raise ValueError("suggestions must not contain empty items")

    def as_dict(self) -> dict[str, Any]:
        """Serialize successful AI feedback."""

        return {
            "status": "completed",
            "explanation": self.explanation,
            "suggestions": list(self.suggestions),
            "quality": self.quality.as_dict(),
            "scoreType": "ai_code_quality_reference",
            "notice": "参考分只评价代码表达质量，不代表题目正确性。",
        }


def classify_execution(result: ExecutionResult) -> RuleAssessment:
    """Classify success, syntax, runtime, timeout and infrastructure outcomes."""

    stderr = result.stderr
    error_type, message = _last_exception(stderr)
    line = _last_source_line(stderr)

    if result.outcome == "success":
        return RuleAssessment(
            "success",
            "success",
            "运行成功",
            "程序在当前输入下正常结束；尚未使用题目测试用例判断答案正确性。",
        )
    if result.outcome == "time_limit":
        return RuleAssessment(
            "time_limit",
            "warning",
            "运行超时",
            "程序超过服务器时间限制，常见原因是死循环或算法复杂度过高。",
        )
    if result.outcome == "output_limit":
        return RuleAssessment(
            "output_limit",
            "warning",
            "输出超限",
            "程序输出超过服务器限制，请检查无限输出或过多调试信息。",
        )
    if result.outcome == "system_error":
        return RuleAssessment(
            "system_error",
            "system",
            "执行环境异常",
            "执行环境未能正常完成任务；这不应被判定为学生代码错误。",
        )
    if result.outcome == "compile_error" or error_type in _SYNTAX_ERRORS:
        detail = _error_detail(error_type, message, line)
        return RuleAssessment(
            "syntax_error",
            "error",
            "语法错误",
            f"Python 无法解析当前代码。{detail}",
            error_type or "SyntaxError",
            line,
        )

    detail = _error_detail(error_type, message, line)
    return RuleAssessment(
        "runtime_error",
        "error",
        "运行错误",
        f"程序已开始执行，但在运行过程中异常终止。{detail}",
        error_type,
        line,
    )


def parse_ai_feedback(text: str) -> AiFeedback:
    """Parse and validate the JSON object returned through AgentRuntime."""

    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("AI response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")

    explanation = payload.get("explanation")
    suggestions = payload.get("suggestions")
    quality = payload.get("quality")
    if not isinstance(explanation, str):
        raise ValueError("AI explanation must be a string")
    if not isinstance(suggestions, list) or not all(
        isinstance(item, str) for item in suggestions
    ):
        raise ValueError("AI suggestions must be a list of strings")
    if not isinstance(quality, dict):
        raise ValueError("AI quality must be an object")
    try:
        rubric = QualityRubric(
            readability=quality["readability"],
            structure=quality["structure"],
            robustness=quality["robustness"],
        )
    except KeyError as exc:
        raise ValueError("AI quality is missing a required dimension") from exc
    return AiFeedback(explanation.strip(), tuple(item.strip() for item in suggestions), rubric)


def _last_exception(stderr: str) -> tuple[str | None, str | None]:
    matches = tuple(_EXCEPTION_PATTERN.finditer(stderr))
    if not matches:
        return None, None
    match = matches[-1]
    return match.group("type").split(".")[-1], match.group("message").strip() or None


def _last_source_line(stderr: str) -> int | None:
    matches = tuple(_LINE_PATTERN.finditer(stderr))
    return int(matches[-1].group("line")) if matches else None


def _error_detail(error_type: str | None, message: str | None, line: int | None) -> str:
    parts: list[str] = []
    if error_type:
        parts.append(f"错误类型：{error_type}")
    if line is not None:
        parts.append(f"位置：第 {line} 行")
    if message:
        parts.append(f"信息：{message}")
    return "；".join(parts) + "。" if parts else ""
