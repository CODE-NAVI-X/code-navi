"""Immutable domain models for versioned programming problems."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


def _non_empty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _positive(value: int, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")


def _tuple(value: Iterable[object], field: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be an iterable")
    try:
        return tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field} must be an iterable") from exc


@dataclass(frozen=True, slots=True)
class TestCase:
    test_id: str
    stdin: str
    expected_output: str
    hidden: bool
    points: int = 1

    def __post_init__(self) -> None:
        _non_empty(self.test_id, "test_id")
        if not isinstance(self.stdin, str) or not isinstance(self.expected_output, str):
            raise ValueError("test input and expected output must be strings")
        if not isinstance(self.hidden, bool):
            raise ValueError("hidden must be a bool")
        _positive(self.points, "points")


@dataclass(frozen=True, slots=True)
class ProblemVersion:
    problem_id: str
    version: int
    language: str
    starter_source: str
    test_cases: tuple[TestCase, ...]
    comparison_policy: str = "exact_normalized"

    def __post_init__(self) -> None:
        _non_empty(self.problem_id, "problem_id")
        _positive(self.version, "version")
        if self.language != "python":
            raise ValueError('language must be "python"')
        if not isinstance(self.starter_source, str):
            raise ValueError("starter_source must be a string")
        if self.comparison_policy != "exact_normalized":
            raise ValueError('comparison_policy must be "exact_normalized"')
        cases = _tuple(self.test_cases, "test_cases")
        if not cases or any(not isinstance(case, TestCase) for case in cases):
            raise ValueError("test_cases must contain at least one TestCase")
        ids = [case.test_id for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("test_id must be unique")
        object.__setattr__(self, "test_cases", cases)


@dataclass(frozen=True, slots=True)
class ProblemDefinition:
    problem_id: str
    title: str
    description: str
    knowledge_tags: tuple[str, ...]
    current_version: int

    def __post_init__(self) -> None:
        _non_empty(self.problem_id, "problem_id")
        _positive(self.current_version, "current_version")
        if not isinstance(self.title, str) or not isinstance(self.description, str):
            raise ValueError("title and description must be strings")
        tags = _tuple(self.knowledge_tags, "knowledge_tags")
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ValueError("knowledge_tags must contain non-empty strings")
        object.__setattr__(self, "knowledge_tags", tags)
