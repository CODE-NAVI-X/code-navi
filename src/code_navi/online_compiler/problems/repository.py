"""Read-only repositories for server-owned problem versions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Protocol

from .models import ProblemVersion


class ProblemRepository(Protocol):
    def get(self, problem_id: str, version: int) -> ProblemVersion | None:
        """Return a known immutable problem version."""


class InMemoryProblemRepository:
    def __init__(self, problems: Iterable[ProblemVersion] = ()) -> None:
        entries: dict[tuple[str, int], ProblemVersion] = {}
        for problem in problems:
            if not isinstance(problem, ProblemVersion):
                raise TypeError("problems must contain ProblemVersion values")
            key = (problem.problem_id, problem.version)
            if key in entries:
                raise ValueError("problem_id and version must be unique")
            entries[key] = problem
        self._problems: Mapping[tuple[str, int], ProblemVersion] = MappingProxyType(entries)

    def get(self, problem_id: str, version: int) -> ProblemVersion | None:
        return self._problems.get((problem_id, version))
