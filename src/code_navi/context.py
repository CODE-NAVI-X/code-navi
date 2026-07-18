"""Bounded project context for CLI questions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod")
_SUMMARY_FILES = ("README.md", "README.rst", "README.txt")
_INLINE_ANCHOR = re.compile(r"(?<!\S)@(?P<value>[\w./\\-]+(?::\d+-\d+)?)")
_ATTACHMENT = re.compile(r"^(?P<path>.+?)(?::(?P<start>\d+)-(?P<end>\d+))?$")


class ContextError(ValueError):
    """A requested context source is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class TaskSummary:
    """Optional project task metadata loaded from .code-navi/task.json."""

    title: str | None = None
    goal: str | None = None
    current_milestone: str | None = None
    active_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileSnippet:
    """A line-bounded file excerpt."""

    path: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """One prior turn in a temporary question branch."""

    user: str
    assistant: str


@dataclass(frozen=True, slots=True)
class ContextSlice:
    """The exact bounded context attached to one assistant request."""

    project_root: Path
    project_name: str
    task: TaskSummary
    project_summary: str | None
    snippets: tuple[FileSnippet, ...]
    previous_answer: str | None
    branch_history: tuple[ConversationTurn, ...]
    sources: tuple[str, ...]

    @property
    def receipt(self) -> str:
        parts = [self.project_name]
        if self.task.current_milestone:
            parts.append(self.task.current_milestone)
        parts.extend(self.sources)
        return " · ".join(dict.fromkeys(parts))

    def render(self) -> str:
        """Render reference data with explicit boundaries for the model."""
        sections = [
            "<project_context>",
            f"Project: {self.project_name}",
            "Project root: .",
        ]
        if self.task.title:
            sections.append(f"Task title: {self.task.title}")
        if self.task.goal:
            sections.append(f"Task goal: {self.task.goal}")
        if self.task.current_milestone:
            sections.append(f"Current milestone: {self.task.current_milestone}")
        if self.task.active_files:
            sections.append("Active files: " + ", ".join(self.task.active_files))
        if self.project_summary:
            sections.extend(("", "Project summary:", self.project_summary))
        for snippet in self.snippets:
            sections.extend(
                (
                    "",
                    f"File {snippet.path}, lines {snippet.start_line}-{snippet.end_line}:",
                    snippet.text,
                )
            )
        if self.previous_answer:
            sections.extend(("", "Previous assistant answer:", self.previous_answer))
        if self.branch_history:
            sections.extend(("", "Temporary question branch history:"))
            for turn in self.branch_history:
                sections.append(f"User: {turn.user}")
                sections.append(f"Assistant: {turn.assistant}")
        sections.append("</project_context>")
        return "\n".join(sections)


@dataclass(frozen=True, slots=True)
class PreparedQuestion:
    """A cleaned user question plus the context attached to it."""

    question: str
    context: ContextSlice

    def runtime_input(self) -> str:
        return f"{self.context.render()}\n\nUser question:\n{self.question}"


def discover_project_root(start: str | Path | None = None) -> Path:
    """Find the nearest project root, falling back to the starting directory."""
    current = Path.cwd() if start is None else Path(start)
    current = current.expanduser().resolve(strict=False)
    if not current.is_dir():
        raise ContextError(f"project path is not a directory: {current}")
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in _PROJECT_MARKERS):
            return candidate
    return current


class ContextBuilder:
    """Build small, auditable context slices rooted in one project."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        include_project_context: bool = True,
        max_context_chars: int = 16_000,
        max_file_lines: int = 200,
    ) -> None:
        root = Path(project_root).expanduser().resolve(strict=False)
        if not root.is_dir():
            raise ContextError(f"project path is not a directory: {root}")
        if max_context_chars < 1 or max_file_lines < 1:
            raise ValueError("context limits must be positive")
        self.project_root = root
        self.include_project_context = include_project_context
        self.max_context_chars = max_context_chars
        self.max_file_lines = max_file_lines

    def prepare(
        self,
        question: str,
        *,
        attachments: tuple[str, ...] = (),
        last_answer: str | None = None,
        branch_history: tuple[ConversationTurn, ...] = (),
    ) -> PreparedQuestion:
        """Resolve inline anchors and produce a context-bounded question."""
        if not isinstance(question, str) or not question.strip():
            raise ContextError("question must not be empty")
        inline = tuple(match.group("value") for match in _INLINE_ANCHOR.finditer(question))
        wants_last = any(value == "last" for value in inline)
        if wants_last and not last_answer:
            raise ContextError("@last is unavailable because there is no previous answer")
        specs = attachments + tuple(value for value in inline if value != "last")
        cleaned = _INLINE_ANCHOR.sub("", question)
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            raise ContextError("question must contain text in addition to context anchors")

        task = self._load_task() if self.include_project_context else TaskSummary()
        summary, summary_source = self._load_project_summary()
        snippets = tuple(self._load_snippet(spec) for spec in specs)
        history = self._bounded_history(branch_history)
        previous = self._tail(last_answer, 4_000) if wants_last else None

        sources: list[str] = []
        if task != TaskSummary():
            sources.append("task.json")
        if summary_source:
            sources.append(summary_source)
        sources.extend(snippet.path for snippet in snippets)
        if previous:
            sources.append("上一条回答")
        if history:
            sources.append("问题分支")

        context = ContextSlice(
            self.project_root,
            self.project_root.name,
            task,
            summary,
            snippets,
            previous,
            history,
            tuple(sources),
        )
        rendered = context.render()
        if len(rendered) > self.max_context_chars:
            raise ContextError(
                "selected context exceeds the configured limit; attach fewer lines or files"
            )
        return PreparedQuestion(cleaned, context)

    def preview(self) -> ContextSlice:
        """Return the default project context without a user question."""
        task = self._load_task() if self.include_project_context else TaskSummary()
        summary, summary_source = self._load_project_summary()
        sources = (summary_source,) if summary_source else ()
        return ContextSlice(
            self.project_root,
            self.project_root.name,
            task,
            summary,
            (),
            None,
            (),
            sources,
        )

    def _load_task(self) -> TaskSummary:
        path = self.project_root / ".code-navi" / "task.json"
        if not path.exists():
            return TaskSummary()
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ContextError(f"invalid task context file: {path}") from exc
        if not isinstance(data, dict):
            raise ContextError("task context must be a JSON object")
        active_files = data.get("active_files", ())
        if not isinstance(active_files, list) or any(
            not isinstance(item, str) for item in active_files
        ):
            raise ContextError("task active_files must be a list of strings")
        for item in active_files:
            candidate = Path(item)
            if (
                not item.strip()
                or candidate.is_absolute()
                or ".." in candidate.parts
                or "\x00" in item
            ):
                raise ContextError("task active_files must be safe project-relative paths")
        fields = {name: data.get(name) for name in ("title", "goal", "current_milestone")}
        if any(value is not None and not isinstance(value, str) for value in fields.values()):
            raise ContextError("task title, goal and current_milestone must be strings")
        return TaskSummary(**fields, active_files=tuple(active_files))

    def _load_project_summary(self) -> tuple[str | None, str | None]:
        if not self.include_project_context:
            return None, None
        for name in _SUMMARY_FILES:
            path = self.project_root / name
            if path.is_file():
                try:
                    value = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    raise ContextError(f"cannot read project summary: {path}") from exc
                return self._head(value, 4_000), name
        return None, None

    def _load_snippet(self, spec: str) -> FileSnippet:
        match = _ATTACHMENT.fullmatch(spec)
        if match is None:
            raise ContextError(f"invalid attachment: {spec}")
        raw_path = match.group("path")
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        path = candidate.resolve(strict=False)
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise ContextError(f"attachment is outside the project: {raw_path}") from exc
        if not path.is_file():
            raise ContextError(f"attachment is not a file: {raw_path}")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ContextError(f"attachment is not readable UTF-8 text: {raw_path}") from exc
        start = int(match.group("start") or 1)
        requested_end = int(match.group("end") or min(len(lines), self.max_file_lines))
        if start < 1 or requested_end < start:
            raise ContextError(f"invalid attachment line range: {spec}")
        end = min(requested_end, start + self.max_file_lines - 1, len(lines))
        if start > len(lines) and lines:
            raise ContextError(f"attachment starts after end of file: {spec}")
        text = "\n".join(lines[start - 1 : end])
        relative = path.relative_to(self.project_root).as_posix()
        return FileSnippet(relative, start, end, text)

    def _bounded_history(
        self, history: tuple[ConversationTurn, ...]
    ) -> tuple[ConversationTurn, ...]:
        bounded = history[-4:]
        return tuple(
            ConversationTurn(self._tail(turn.user, 1_000), self._tail(turn.assistant, 2_000))
            for turn in bounded
        )

    @staticmethod
    def _head(value: str, limit: int) -> str:
        return value if len(value) <= limit else value[:limit] + "\n…[truncated]"

    @staticmethod
    def _tail(value: str | None, limit: int) -> str:
        if not value:
            return ""
        return value if len(value) <= limit else "[truncated]…\n" + value[-limit:]


__all__ = [
    "ContextBuilder",
    "ContextError",
    "ContextSlice",
    "ConversationTurn",
    "FileSnippet",
    "PreparedQuestion",
    "TaskSummary",
    "discover_project_root",
]
