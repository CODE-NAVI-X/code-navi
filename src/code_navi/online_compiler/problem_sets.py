"""Practice-set generation from built-in and session-owned compiler problems."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .problem_imports import DIFFICULTY_ORDER
from .problems.catalog import DEFAULT_PROBLEM_DEFINITIONS, DEFAULT_PROBLEM_VERSIONS
from .problems.models import ProblemDefinition, ProblemVersion

MAX_PRACTICE_SET_SIZE = 12
DEFAULT_PRACTICE_SET_SIZE = 5

BUILT_IN_HINTS: dict[str, tuple[str, str, str]] = {
    "temperature-convert": ("easy", "一行摄氏温度", "对应华氏温度，保留两位小数"),
    "leap-year": ("easy", "一行年份整数", "LEAP 或 COMMON"),
    "digit-sum": ("medium", "一行非负整数", "各位数字之和"),
    "palindrome": ("medium", "一行字符串", "YES 或 NO"),
    "list-sum": ("medium", "空格分隔的整数", "一个整数总和"),
    "word-frequency": ("hard", "空格分隔的单词", "最高频单词和次数"),
    "bracket-match": ("hard", "一行括号字符串", "VALID 或 INVALID"),
}


@dataclass(frozen=True, slots=True)
class PracticeSetProblem:
    id: str
    source: str
    title: str
    description: str
    difficulty: str
    tags: tuple[str, ...]
    starter_code: str
    input_hint: str
    output_hint: str
    sample_tests: tuple[dict[str, str], ...]
    judgeable: bool
    generation_reason: str
    limitations: tuple[str, ...]
    problem_id: str | None = None
    problem_version: int | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "tags": list(self.tags),
            "starterCode": self.starter_code,
            "inputHint": self.input_hint,
            "outputHint": self.output_hint,
            "sampleTests": list(self.sample_tests),
            "judgeable": self.judgeable,
            "generationReason": self.generation_reason,
            "limitations": list(self.limitations),
        }
        if self.problem_id is not None:
            payload["problemId"] = self.problem_id
            payload["problemVersion"] = self.problem_version or 1
        return payload


@dataclass(frozen=True, slots=True)
class PracticeSetResult:
    source: str
    ordered_problems: tuple[PracticeSetProblem, ...]
    rationale: str
    coverage: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "orderedProblems": [problem.as_dict() for problem in self.ordered_problems],
            "rationale": self.rationale,
            "coverage": list(self.coverage),
            "warnings": list(self.warnings),
        }


def build_practice_set(
    *,
    prompt: str,
    target_count: int = DEFAULT_PRACTICE_SET_SIZE,
    difficulty_range: tuple[str, str] = ("easy", "hard"),
    knowledge_tags: tuple[str, ...] = (),
    include_uploaded: bool = True,
    uploaded_problems: tuple[dict[str, Any], ...] = (),
) -> PracticeSetResult:
    """Build a deterministic practice set before optional AI reordering."""

    candidates = _built_in_candidates()
    if include_uploaded:
        candidates.extend(_uploaded_candidates(uploaded_problems))
    filtered = _filter_candidates(candidates, difficulty_range, knowledge_tags)
    ordered = sorted(
        filtered,
        key=lambda problem: (
            -_match_score(problem, prompt, knowledge_tags),
            DIFFICULTY_ORDER.get(problem.difficulty, 99),
            0 if problem.source == "built_in" else 1,
            problem.title,
        ),
    )
    selected = ordered[:target_count]
    if len(selected) < target_count:
        selected.extend(_generated_candidates(prompt, target_count - len(selected), knowledge_tags))

    sequenced = tuple(
        _with_sequence_reason(problem, index) for index, problem in enumerate(selected)
    )
    warnings: list[str] = []
    if any(problem.source != "built_in" for problem in sequenced):
        warnings.append("上传题和生成题仅支持运行与 AI 评析，不支持服务端隐藏测试判题。")
    if len(filtered) < target_count:
        warnings.append("候选题库不足，已补充不可判题的生成题。")
    return PracticeSetResult(
        source="deterministic_rule",
        ordered_problems=sequenced,
        rationale=_rationale(prompt, sequenced),
        coverage=tuple(_coverage(sequenced)),
        warnings=tuple(warnings),
    )


def apply_practice_set_plan(
    base: PracticeSetResult,
    planner_payload: dict[str, Any],
) -> PracticeSetResult:
    """Apply validated AI ordering metadata without changing problem facts."""

    suggestions = planner_payload.get("orderedProblems")
    if not isinstance(suggestions, list):
        raise ValueError("AI planner response must contain orderedProblems")
    known = {problem.id: problem for problem in base.ordered_problems}
    ordered: list[PracticeSetProblem] = []
    seen: set[str] = set()
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        problem_id = suggestion.get("id")
        if not isinstance(problem_id, str) or problem_id not in known or problem_id in seen:
            continue
        base_problem = known[problem_id]
        reason = suggestion.get("generationReason")
        ordered.append(
            replace(
                base_problem,
                generation_reason=(
                    reason.strip()
                    if isinstance(reason, str) and reason.strip()
                    else base_problem.generation_reason
                ),
            )
        )
        seen.add(problem_id)
    ordered.extend(problem for problem in base.ordered_problems if problem.id not in seen)
    rationale = planner_payload.get("rationale")
    coverage = planner_payload.get("coverage")
    warnings = planner_payload.get("warnings")
    planner_warnings = (
        [item.strip() for item in warnings if isinstance(item, str) and item.strip()]
        if isinstance(warnings, list)
        else []
    )
    return PracticeSetResult(
        source="rules_with_ai_planning",
        ordered_problems=tuple(ordered),
        rationale=(
            rationale.strip()
            if isinstance(rationale, str) and rationale.strip()
            else base.rationale
        ),
        coverage=(
            tuple(item.strip() for item in coverage if isinstance(item, str) and item.strip())[:8]
            if isinstance(coverage, list)
            else base.coverage
        ),
        warnings=tuple(
            dict.fromkeys(
                [
                    *base.warnings,
                    *planner_warnings,
                ]
            )
        )[:8],
    )


def _built_in_candidates() -> list[PracticeSetProblem]:
    versions = {version.problem_id: version for version in DEFAULT_PROBLEM_VERSIONS}
    return [
        _built_in_problem(definition, versions[definition.problem_id])
        for definition in DEFAULT_PROBLEM_DEFINITIONS
        if definition.problem_id in versions
    ]


def _built_in_problem(
    definition: ProblemDefinition, version: ProblemVersion
) -> PracticeSetProblem:
    difficulty, input_hint, output_hint = BUILT_IN_HINTS.get(
        definition.problem_id,
        ("medium", "按题目描述读取标准输入", "按题目要求输出结果"),
    )
    public_tests = tuple(
        {"stdin": test.stdin, "expectedOutput": test.expected_output}
        for test in version.test_cases
        if not test.hidden
    )
    return PracticeSetProblem(
        id=f"built_in:{definition.problem_id}",
        source="built_in",
        title=definition.title,
        description=definition.description,
        difficulty=difficulty,
        tags=definition.knowledge_tags,
        starter_code=version.starter_source,
        input_hint=input_hint,
        output_hint=output_hint,
        sample_tests=public_tests,
        judgeable=True,
        generation_reason="服务端内置题，具备公开样例和隐藏测试，可用于提交判题。",
        limitations=(),
        problem_id=definition.problem_id,
        problem_version=definition.current_version,
    )


def _uploaded_candidates(uploaded: tuple[dict[str, Any], ...]) -> list[PracticeSetProblem]:
    candidates: list[PracticeSetProblem] = []
    for index, item in enumerate(uploaded[:MAX_PRACTICE_SET_SIZE]):
        if not isinstance(item, dict):
            continue
        title = _string(item.get("title"), f"上传题目 {index + 1}")
        candidates.append(
            PracticeSetProblem(
                id=f"uploaded:{_string(item.get('id') or item.get('importId'), str(index + 1))}",
                source="uploaded",
                title=title,
                description=_string(item.get("description"), "根据上传内容完成编程题。"),
                difficulty=_difficulty(item.get("difficulty")),
                tags=tuple(_strings(item.get("tags"))) or ("上传",),
                starter_code=_string(item.get("starterCode") or item.get("source"), "# TODO\n"),
                input_hint=_string(item.get("inputHint"), "按题目描述读取标准输入"),
                output_hint=_string(item.get("outputHint"), "按题目要求输出结果"),
                sample_tests=tuple(_sample_tests(item.get("sampleTests"))),
                judgeable=False,
                generation_reason=f"来自本次会话上传题：{title}。",
                limitations=("未进入服务端题库，不支持隐藏测试判题。",),
            )
        )
    return candidates


def _generated_candidates(
    prompt: str,
    count: int,
    knowledge_tags: tuple[str, ...],
) -> list[PracticeSetProblem]:
    topic = prompt.strip()[:28] or "当前学习目标"
    tags = knowledge_tags or ("综合练习",)
    return [
        PracticeSetProblem(
            id=f"generated:{index + 1}",
            source="generated",
            title=f"{topic} 练习 {index + 1}",
            description=f"围绕“{topic}”设计的开放练习，请根据输入输出要求完成程序。",
            difficulty="medium",
            tags=tags,
            starter_code="# TODO: read input and complete the solution\n",
            input_hint="按题目描述读取标准输入",
            output_hint="按题目要求输出结果",
            sample_tests=(),
            judgeable=False,
            generation_reason="现有题库不足时补充的练习题，只用于运行和 AI 评析。",
            limitations=("AI 生成题没有服务端隐藏测试，不能提交判题。",),
        )
        for index in range(max(0, count))
    ]


def _filter_candidates(
    candidates: list[PracticeSetProblem],
    difficulty_range: tuple[str, str],
    knowledge_tags: tuple[str, ...],
) -> list[PracticeSetProblem]:
    low, high = [DIFFICULTY_ORDER.get(item, 0) for item in difficulty_range]
    tags = {tag.lower() for tag in knowledge_tags}
    filtered = [
        problem
        for problem in candidates
        if low <= DIFFICULTY_ORDER.get(problem.difficulty, 99) <= high
    ]
    if tags:
        matching = [
            problem
            for problem in filtered
            if any(tag.lower() in tags for tag in problem.tags)
        ]
        return matching or filtered
    return filtered


def _match_score(
    problem: PracticeSetProblem, prompt: str, knowledge_tags: tuple[str, ...]
) -> int:
    haystack = " ".join([problem.title, problem.description, *problem.tags]).lower()
    normalized_prompt = prompt.lower()
    words = [word for word in normalized_prompt.replace("/", " ").split() if len(word) >= 2]
    score = sum(2 for word in words if word in haystack)
    score += sum(3 for tag in knowledge_tags if tag.lower() in haystack)
    score += sum(4 for tag in problem.tags if tag.lower() in normalized_prompt)
    return score


def _with_sequence_reason(problem: PracticeSetProblem, index: int) -> PracticeSetProblem:
    prefix = f"第 {index + 1} 题："
    if problem.generation_reason.startswith(prefix):
        return problem
    return replace(problem, generation_reason=prefix + problem.generation_reason)


def _rationale(prompt: str, problems: tuple[PracticeSetProblem, ...]) -> str:
    goal = prompt.strip() or "当前学习目标"
    return f"围绕“{goal}”按难度和知识点递进排列，共 {len(problems)} 道题。"


def _coverage(problems: tuple[PracticeSetProblem, ...]) -> list[str]:
    seen: list[str] = []
    for problem in problems:
        for tag in problem.tags:
            if tag not in seen:
                seen.append(tag)
    return seen[:8]


def _string(value: object, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()][:6]


def _difficulty(value: object) -> str:
    return value if value in {"easy", "medium", "hard"} else "medium"


def _sample_tests(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    samples: list[dict[str, str]] = []
    for sample in value[:4]:
        if not isinstance(sample, dict):
            continue
        stdin = sample.get("stdin")
        expected = sample.get("expectedOutput")
        if isinstance(stdin, str) and isinstance(expected, str):
            samples.append({"stdin": stdin, "expectedOutput": expected})
    return samples
