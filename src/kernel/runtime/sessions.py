"""Thin Event-only persistence helpers for one runtime invocation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kernel.adapters.jsonl_session import save_session
from kernel.core import Event

_INVALID_WINDOWS_FILENAME_CHARS = frozenset('<>:"|?*')


def validate_path_segment(value: str, field_name: str = "path segment") -> str:
    """Validate one untrusted directory or filename component."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if (
        value in {".", ".."}
        or "\x00" in value
        or "/" in value
        or "\\" in value
        or any(character in value for character in _INVALID_WINDOWS_FILENAME_CHARS)
        or Path(value).is_absolute()
    ):
        raise ValueError(f"{field_name} must be a single safe path segment")
    return value


def session_log_path(session_dir: str | Path, session_id: str | None, run_id: str) -> Path:
    """Return the append-only JSONL path for one runtime invocation."""
    if not isinstance(session_dir, (str, Path)):
        raise TypeError("session_dir must be a path")
    run_segment = validate_path_segment(run_id, "run_id")
    root = Path(session_dir)
    if session_id is None:
        return root / f"{run_segment}.jsonl"
    session_segment = validate_path_segment(session_id, "session_id")
    return root / session_segment / f"{run_segment}.jsonl"


def save_runtime_events(
    session_dir: str | Path,
    session_id: str | None,
    run_id: str,
    events: Sequence[Event],
) -> str:
    """Persist only the Event log for one run and return its path."""
    path = session_log_path(session_dir, session_id, run_id)
    save_session(path, events)
    return str(path)
