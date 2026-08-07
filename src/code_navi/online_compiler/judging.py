"""Deterministic server-side judging with hidden-test redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .piston import ExecutionLimits, ExecutionResult
from .problems.models import ProblemVersion


class ExecutionRunner(Protocol):
    def execute_python(
        self, source: str, stdin: str, *, version: str, limits: ExecutionLimits
    ) -> ExecutionResult: ...


@dataclass(frozen=True, slots=True)
class TestResult:
    test_id: str
    index: int
    status: str
    points: int
    hidden: bool
    stdout: str | None
    stderr: str | None
    error_type: str | None

    def as_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "index": self.index,
            "status": self.status,
            "points": self.points,
            "hidden": self.hidden,
        }
        if not self.hidden:
            body.update(
                {
                    "testId": self.test_id,
                    "stdout": self.stdout,
                    "stderr": self.stderr,
                    "errorType": self.error_type,
                }
            )
        return body


@dataclass(frozen=True, slots=True)
class JudgeResult:
    verdict: str
    score: float
    passed: int
    total: int
    passed_points: int
    total_points: int
    test_results: tuple[TestResult, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "passed": self.passed,
            "total": self.total,
            "passedPoints": self.passed_points,
            "totalPoints": self.total_points,
            "testResults": [item.as_dict() for item in self.test_results],
        }


_OUTCOMES = {"compile_error", "runtime_error", "time_limit", "output_limit", "system_error"}
_PRIORITY = {
    "passed": 0,
    "wrong_answer": 1,
    "runtime_error": 2,
    "output_limit": 3,
    "time_limit": 4,
    "compile_error": 5,
    "system_error": 6,
}
_EXCEPTION = re.compile(r"(?m)^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?::|$)")


def judge_submission(
    source: str,
    problem: ProblemVersion,
    runner: ExecutionRunner,
    runtime_version: str,
    limits: ExecutionLimits,
) -> JudgeResult:
    results: list[TestResult] = []
    for index, case in enumerate(problem.test_cases):
        execution = runner.execute_python(
            source, case.stdin, version=runtime_version, limits=limits
        )
        status = _status(execution, case.expected_output)
        passed = status == "passed"
        results.append(
            TestResult(
                case.test_id,
                index,
                status,
                case.points if passed else 0,
                case.hidden,
                None if case.hidden else execution.stdout,
                None if case.hidden else execution.stderr,
                None if case.hidden else _error_type(execution),
            )
        )
    total_points = sum(case.points for case in problem.test_cases)
    passed_points = sum(item.points for item in results)
    worst = max((item.status for item in results), key=_PRIORITY.__getitem__)
    return JudgeResult(
        "accepted" if worst == "passed" else worst,
        round(passed_points / total_points * 100, 2),
        sum(item.status == "passed" for item in results),
        len(results),
        passed_points,
        total_points,
        tuple(results),
    )


def _status(execution: ExecutionResult, expected: str) -> str:
    if execution.outcome != "success":
        return execution.outcome if execution.outcome in _OUTCOMES else "system_error"
    return "passed" if _normalize(execution.stdout) == _normalize(expected) else "wrong_answer"


def _normalize(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return value[:-1] if value.endswith("\n") else value


def _error_type(execution: ExecutionResult) -> str | None:
    matches = tuple(_EXCEPTION.finditer(execution.stderr))
    return matches[-1].group("type").split(".")[-1] if matches else None
