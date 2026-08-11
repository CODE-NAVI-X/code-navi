"""Deterministic parsing for student-uploaded programming exercise text."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any

DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
TAG_ORDER = {
    "输入输出": 0,
    "分支": 1,
    "循环": 2,
    "字符串": 3,
    "列表": 4,
    "字典": 5,
    "栈": 6,
    "算法": 7,
}
MAX_IMPORTED_PROBLEMS = 12


@dataclass(frozen=True, slots=True)
class ImportedSampleTest:
    stdin: str
    expected_output: str

    def as_dict(self) -> dict[str, str]:
        return {"stdin": self.stdin, "expectedOutput": self.expected_output}


@dataclass(frozen=True, slots=True)
class ImportedProblem:
    import_id: str
    title: str
    description: str
    difficulty: str
    tags: tuple[str, ...]
    input_hint: str
    output_hint: str
    starter_code: str
    sample_tests: tuple[ImportedSampleTest, ...]
    confidence: float
    warnings: tuple[str, ...]
    order_reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "importId": self.import_id,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "tags": list(self.tags),
            "inputHint": self.input_hint,
            "outputHint": self.output_hint,
            "starterCode": self.starter_code,
            "sampleTests": [sample.as_dict() for sample in self.sample_tests],
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "orderReason": self.order_reason,
        }


def analyze_problem_text(text: str, *, filename: str | None = None) -> list[ImportedProblem]:
    """Extract a small ordered set of practice exercises from pasted text."""

    normalized = _normalize_text(text)
    structured = _parse_structured_upload(normalized, filename)
    if structured is not None:
        normalized = structured
    if not normalized.strip():
        return []
    chunks = _split_problem_chunks(normalized)
    problems = [
        _problem_from_chunk(index, chunk)
        for index, chunk in enumerate(chunks)
        if _has_problem_signal(chunk)
    ]
    return sorted(
        problems,
        key=lambda item: (
            DIFFICULTY_ORDER[item.difficulty],
            min(TAG_ORDER.get(tag, 99) for tag in item.tags),
            item.title,
        ),
    )


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _split_problem_chunks(text: str) -> list[str]:
    matches = list(
        re.finditer(
            r"(?m)^(?:#{1,3}\s*)?(?:题目|练习|Problem|Exercise)\s*[\d一二三四五六七八九十]*[：:.\s-]*(.*)$",
            text,
        )
    )
    if len(matches) <= 1:
        return [text]

    chunks: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[match.start() : end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks[:MAX_IMPORTED_PROBLEMS]


def _problem_from_chunk(index: int, chunk: str) -> ImportedProblem:
    title = _extract_title(chunk, index)
    description = _extract_description(chunk, title)
    input_hint = _extract_section(chunk, ("输入", "Input")) or "按题目描述读取标准输入"
    output_hint = _extract_section(chunk, ("输出", "Output")) or "按题目要求输出结果"
    sample_tests = _extract_sample_tests(chunk)
    tags = _infer_tags(chunk)
    difficulty = _infer_difficulty(chunk, tags)
    warnings = _warnings(input_hint, output_hint, sample_tests)
    confidence = _confidence(description, input_hint, output_hint, warnings)
    return ImportedProblem(
        import_id=f"uploaded-{index + 1}",
        title=title,
        description=description,
        difficulty=difficulty,
        tags=tags,
        input_hint=input_hint,
        output_hint=output_hint,
        starter_code=_starter_code(input_hint, tags),
        sample_tests=sample_tests,
        confidence=confidence,
        warnings=warnings,
        order_reason=_order_reason(difficulty, tags),
    )


def _extract_title(chunk: str, index: int) -> str:
    for line in chunk.splitlines():
        stripped = line.strip(" #\t")
        if not stripped:
            continue
        match = re.match(
            r"^(?:题目|练习|Problem|Exercise)\s*[\d一二三四五六七八九十]*[：:.\s-]*(.+)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if match and match.group(1).strip():
            return _clip(match.group(1).strip(), 40)
        if len(stripped) <= 40 and not _is_section_heading(stripped):
            return _clip(stripped, 40)
    return f"上传题目 {index + 1}"


def _extract_description(chunk: str, title: str) -> str:
    lines: list[str] = []
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped or stripped == title or _is_section_heading(stripped):
            continue
        if re.match(
            r"^(?:题目|练习|Problem|Exercise)\s*[\d一二三四五六七八九十]*[：:.\s-]*",
            stripped,
            flags=re.IGNORECASE,
        ):
            continue
        if re.match(r"^(?:输入|输出|Input|Output)(?:说明)?\s*[：:]", stripped, re.IGNORECASE):
            continue
        if stripped.startswith(("样例", "示例", "Sample")):
            break
        stripped = re.sub(r"^(?:题目描述|描述)\s*[：:]\s*", "", stripped)
        lines.append(stripped)
        if len(" ".join(lines)) >= 240:
            break
    return _clip(" ".join(lines), 360) or "根据上传内容完成编程题。"


def _extract_section(chunk: str, names: tuple[str, ...]) -> str | None:
    lines = chunk.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for name in names:
            if re.match(rf"^{re.escape(name)}(?:说明)?\s*[：:]?", stripped, re.IGNORECASE):
                inline = re.sub(
                    rf"^{re.escape(name)}(?:说明)?\s*[：:]?\s*",
                    "",
                    stripped,
                    flags=re.IGNORECASE,
                ).strip()
                if inline:
                    return _clip(inline, 120)
                following = _next_content_line(lines[index + 1 :])
                return _clip(following, 120) if following else None
    return None


def _extract_sample_tests(chunk: str) -> tuple[ImportedSampleTest, ...]:
    lines = chunk.splitlines()
    samples: list[ImportedSampleTest] = []
    for index, line in enumerate(lines):
        if not re.match(r"^(样例|示例|Sample)\s*(\d+)?\s*[：:]?", line.strip(), re.I):
            continue
        block = lines[index + 1 : index + 7]
        stdin = _section_value(block, ("输入", "Input"))
        output = _section_value(block, ("输出", "Output"))
        if stdin and output:
            samples.append(ImportedSampleTest(stdin, output))
        elif len(block) >= 2:
            values = [item.strip() for item in block if item.strip()]
            if len(values) >= 2:
                samples.append(ImportedSampleTest(values[0], values[1]))
    return tuple(samples[:4])


def _section_value(lines: list[str], names: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines):
        stripped = line.strip()
        for name in names:
            if re.match(rf"^{re.escape(name)}\s*[：:]", stripped, re.I):
                return _clip(
                    re.sub(rf"^{re.escape(name)}\s*[：:]\s*", "", stripped, flags=re.I),
                    500,
                )
            if re.match(rf"^{re.escape(name)}\s*$", stripped, re.I):
                following = _next_content_line(lines[index + 1 :])
                return _clip(following, 500) if following else None
    return None


def _parse_structured_upload(text: str, filename: str | None) -> str | None:
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    if suffix == "json" or text.lstrip().startswith(("[", "{")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return ""
        records = (
            payload
            if isinstance(payload, list)
            else payload.get("problems")
            if isinstance(payload, dict)
            else None
        )
        if not isinstance(records, list):
            return ""
        chunks = [_json_record_to_chunk(record, index) for index, record in enumerate(records)]
        return "\n\n".join(chunk for chunk in chunks if chunk)
    if suffix == "csv":
        try:
            rows = csv.DictReader(io.StringIO(text))
            chunks = [_json_record_to_chunk(row, index) for index, row in enumerate(rows)]
        except csv.Error:
            return ""
        return "\n\n".join(chunk for chunk in chunks if chunk)
    return None


def _has_problem_signal(chunk: str) -> bool:
    has_title = bool(
        re.search(
            r"(?im)^(?:#{1,3}\s*)?(?:题目|练习|Problem|Exercise)\s*[\d一二三四五六七八九十]*[：:.\s-]*\S+",
            chunk,
        )
    )
    has_description = bool(re.search(r"(?im)^(?:题目描述|描述|Description)\s*[：:]\s*\S+", chunk))
    has_input = _extract_section(chunk, ("输入", "Input")) is not None
    has_output = _extract_section(chunk, ("输出", "Output")) is not None
    has_sample = bool(_extract_sample_tests(chunk))
    if has_input and has_output:
        return True
    return has_title and (has_description or has_input or has_output or has_sample)


def _json_record_to_chunk(record: Any, index: int) -> str:
    if not isinstance(record, dict):
        return ""
    title = record.get("title") or record.get("name") or f"上传题目 {index + 1}"
    description = record.get("description") or record.get("statement") or ""
    input_hint = record.get("inputHint") or record.get("input") or ""
    output_hint = record.get("outputHint") or record.get("output") or ""
    samples = record.get("sampleTests") or record.get("samples") or []
    lines = [f"题目：{title}", f"描述：{description}"]
    if input_hint:
        lines.append(f"输入：{input_hint}")
    if output_hint:
        lines.append(f"输出：{output_hint}")
    if isinstance(samples, list):
        for sample in samples[:4]:
            if isinstance(sample, dict):
                stdin = sample.get("stdin") or sample.get("input")
                expected = sample.get("expectedOutput") or sample.get("output")
                if stdin is not None and expected is not None:
                    lines.extend(["样例：", f"输入：{stdin}", f"输出：{expected}"])
    return "\n".join(lines)


def _next_content_line(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_section_heading(stripped):
            return None
        return stripped
    return None


def _is_section_heading(value: str) -> bool:
    return bool(
        re.match(
            r"^(题目描述|描述|输入|输入说明|输出|输出说明|样例|示例|Sample|Input|Output)\s*[：:]?$",
            value,
            flags=re.IGNORECASE,
        )
    )


def _infer_tags(chunk: str) -> tuple[str, ...]:
    rules = (
        ("栈", ("栈", "括号", "stack")),
        ("字典", ("字典", "映射", "频次", "频率", "统计", "dict", "map")),
        ("列表", ("列表", "数组", "list", "array")),
        ("字符串", ("字符串", "字符", "回文", "单词", "string")),
        ("循环", ("循环", "遍历", "累加", "求和", "for", "while")),
        ("分支", ("判断", "如果", "条件", "闰年", "if", "else")),
    )
    lowered = chunk.lower()
    tags = [
        tag for tag, keywords in rules if any(keyword.lower() in lowered for keyword in keywords)
    ]
    if not tags:
        tags.append("输入输出")
    return tuple(tags[:4])


def _infer_difficulty(chunk: str, tags: tuple[str, ...]) -> str:
    lowered = chunk.lower()
    if any(word in lowered for word in ("挑战", "困难", "hard", "栈", "动态规划", "图")):
        return "hard"
    if any(word in lowered for word in ("进阶", "中等", "medium", "字典", "统计", "排序")):
        return "medium"
    if any(tag in {"字典", "栈", "算法"} for tag in tags):
        return "medium"
    return "easy"


def _warnings(
    input_hint: str,
    output_hint: str,
    sample_tests: tuple[ImportedSampleTest, ...],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if input_hint == "按题目描述读取标准输入":
        warnings.append("未识别到明确输入说明，请人工确认。")
    if output_hint == "按题目要求输出结果":
        warnings.append("未识别到明确输出说明，请人工确认。")
    if not sample_tests:
        warnings.append("未识别到样例，当前题目只支持运行与练习，不支持服务端判题。")
    return tuple(warnings)


def _confidence(
    description: str, input_hint: str, output_hint: str, warnings: tuple[str, ...]
) -> float:
    score = 0.35
    if description != "根据上传内容完成编程题。":
        score += 0.25
    if input_hint != "按题目描述读取标准输入":
        score += 0.2
    if output_hint != "按题目要求输出结果":
        score += 0.2
    return max(0.1, round(score - len(warnings) * 0.08, 2))


def _starter_code(input_hint: str, tags: tuple[str, ...]) -> str:
    if "栈" in tags:
        return "text = input().strip()\nstack = []\n\n# TODO: complete the solution\n"
    if "列表" in tags or "循环" in tags:
        return "values = input().split()\n\n# TODO: complete the solution\n"
    if "字符串" in tags:
        return "text = input().strip()\n\n# TODO: complete the solution\n"
    if "分支" in tags:
        return "value = input().strip()\n\n# TODO: complete the solution\n"
    if "整数" in input_hint or "数字" in input_hint:
        return "number = int(input())\n\n# TODO: complete the solution\n"
    return "# TODO: read input and complete the solution\n"


def _order_reason(difficulty: str, tags: tuple[str, ...]) -> str:
    label = {"easy": "基础", "medium": "进阶", "hard": "挑战"}[difficulty]
    return f"按{label}难度和{'、'.join(tags)}知识点放入当前练习序列。"


def _clip(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"
