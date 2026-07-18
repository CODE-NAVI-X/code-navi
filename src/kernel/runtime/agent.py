"""Stable host-level contracts for selecting and running one agent."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from kernel.core import Event, KernelConfig, Message, RunResult


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _json_object(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    try:
        encoded = json.dumps(dict(value), ensure_ascii=False, allow_nan=False)
        normalized = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise TypeError(f"{field_name} must normalize to a JSON object")
    return normalized


def _tool_names(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError("tool_names must be a sequence of strings")
    try:
        names = tuple(value)
    except TypeError as exc:
        raise TypeError("tool_names must be a sequence of strings") from exc
    for name in names:
        _non_empty_string(name, "tool_names item")
    if len(set(names)) != len(names):
        raise ValueError("tool_names must not contain duplicates")
    return names


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Declarative domain-owned agent definition."""

    name: str
    description: str
    system_prompt: str
    tool_names: tuple[str, ...] = ()
    default_config: KernelConfig | None = None
    output_format: str = "markdown"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _non_empty_string(self.name, "name"))
        object.__setattr__(self, "description", _non_empty_string(self.description, "description"))
        object.__setattr__(
            self,
            "system_prompt",
            _non_empty_string(self.system_prompt, "system_prompt"),
        )
        object.__setattr__(self, "tool_names", _tool_names(self.tool_names))
        if self.default_config is not None and not isinstance(self.default_config, KernelConfig):
            raise TypeError("default_config must be KernelConfig or None")
        object.__setattr__(
            self,
            "output_format",
            _non_empty_string(self.output_format, "output_format"),
        )


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    """Input supplied by a host for exactly one kernel run."""

    user_input: str
    session_id: str | None = None
    run_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_input", _non_empty_string(self.user_input, "user_input"))
        for field_name in ("session_id", "run_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _non_empty_string(value, field_name))
        object.__setattr__(self, "metadata", _json_object(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Host-friendly projection of the unchanged kernel RunResult."""

    agent_name: str
    run_id: str
    session_id: str | None
    run_result: RunResult
    events: tuple[Event, ...]
    final_messages: tuple[Message, ...]
    output_text: str | None = None
    event_log_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_name", _non_empty_string(self.agent_name, "agent_name"))
        object.__setattr__(self, "run_id", _non_empty_string(self.run_id, "run_id"))
        if self.session_id is not None:
            object.__setattr__(self, "session_id", _non_empty_string(self.session_id, "session_id"))
        if not isinstance(self.run_result, RunResult):
            raise TypeError("run_result must be RunResult")
        events = tuple(self.events)
        if any(not isinstance(event, Event) for event in events):
            raise TypeError("events must contain Event values")
        messages = tuple(self.final_messages)
        if any(not isinstance(message, Message) for message in messages):
            raise TypeError("final_messages must contain Message values")
        if self.output_text is not None and not isinstance(self.output_text, str):
            raise TypeError("output_text must be str or None")
        if self.event_log_path is not None and not isinstance(self.event_log_path, str):
            raise TypeError("event_log_path must be str or None")
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "final_messages", messages)
