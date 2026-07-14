"""Stable kernel-native contracts for the S2/S3 boundary.

No loop progression, host behavior, provider SDK integration, or domain policy
belongs here. This is the contract layer consumed by loop, adapter, and tool
layers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

JsonObject = dict[str, Any]
EVENT_TYPES = frozenset(
    {
        "run_started",
        "message_added",
        "tool_called",
        "tool_returned",
        "budget_updated",
        "context_compressed",
        "interrupted",
        "error",
        "run_finished",
    }
)
ERROR_SOURCES = frozenset({"provider", "tool", "kernel"})
ERROR_CLASSIFICATIONS = frozenset({"retryable", "fatal"})
CONTENT_BLOCK_TYPES = frozenset(
    {"text", "tool_use", "tool_result", "image_ref", "artifact_ref"}
)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("value must be JSON-serializable") from exc
    return value


def _obj(value: Mapping[str, Any] | None) -> JsonObject:
    return dict(_json_safe({} if value is None else value))


def _tuple(cls: Any, values: Sequence[Mapping[str, Any]]) -> tuple[Any, ...]:
    return tuple(cls.from_json(value) for value in values)


def _required_ints(payload: Mapping[str, Any], keys: Sequence[str]) -> dict[str, int]:
    values: dict[str, int] = {}
    for key in keys:
        if key not in payload or not isinstance(payload[key], int):
            raise ValueError(f"payload requires int field: {key}")
        values[key] = payload[key]
    return values


def _validate_error_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("source") not in ERROR_SOURCES:
        raise ValueError("error payload source must be provider, tool, or kernel")
    if payload.get("classification") not in ERROR_CLASSIFICATIONS:
        raise ValueError("error payload classification must be retryable or fatal")
    if not isinstance(payload.get("message"), str):
        raise ValueError("error payload message must be str")
    attempt = payload.get("attempt")
    if attempt is not None and (not isinstance(attempt, int) or attempt < 1):
        raise ValueError("error payload attempt must be None or int >= 1")


def _validate_context_compressed_payload(payload: Mapping[str, Any]) -> None:
    if any(
        not isinstance(payload.get(key), int) or isinstance(payload.get(key), bool)
        for key in ("start_seq", "end_seq")
    ):
        raise ValueError("context_compressed seq bounds must be int")
    bounds = _required_ints(payload, ("start_seq", "end_seq"))
    if bounds["start_seq"] < 0 or bounds["end_seq"] < bounds["start_seq"]:
        raise ValueError("context_compressed payload requires a valid seq range")
    source_ids = payload.get("source_event_ids")
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or any(not isinstance(item, str) or not item for item in source_ids)
        or len(set(source_ids)) != len(source_ids)
    ):
        raise ValueError(
            "context_compressed payload source_event_ids must be unique strings"
        )
    if not isinstance(payload.get("summary"), str):
        raise ValueError("context_compressed payload summary must be str")
    previous = payload.get("previous_event_id")
    if previous is not None and (not isinstance(previous, str) or not previous):
        raise ValueError(
            "context_compressed payload previous_event_id must be None or str"
        )


class ToolPermission(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    EXECUTE = "EXECUTE"
    NETWORK = "NETWORK"
    SENSITIVE = "SENSITIVE"
    PUBLISH = "PUBLISH"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INTERRUPTED = "interrupted"
    FATAL_ERROR = "fatal_error"

    @property
    def is_terminal(self) -> bool:
        return self is not RunStatus.RUNNING


class RetryableProviderError(Exception):
    """Provider failure that S3 loop may retry within configured bounds."""


class FatalProviderError(Exception):
    """Provider failure that S3 loop must not retry."""


class ToolDispatcher(Protocol):
    """Single tool execution boundary used by the S3 loop."""

    def dispatch(self, call: "ToolCall") -> "ToolResult":
        ...


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    args: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("ToolCall id and name are required")
        object.__setattr__(self, "args", _obj(self.args))

    def to_json(self) -> JsonObject:
        return {"id": self.id, "name": self.name, "args": self.args}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ToolCall":
        return cls(str(data["id"]), str(data["name"]), _obj(data.get("args")))


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_call_id: str
    name: str
    result: Any = None
    error: str | None = None
    permissions: frozenset[ToolPermission] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.tool_call_id or not self.name:
            raise ValueError("ToolResult tool_call_id and name are required")
        object.__setattr__(self, "result", _json_safe(self.result))
        object.__setattr__(
            self, "permissions", frozenset(ToolPermission(item) for item in self.permissions)
        )

    def to_json(self) -> JsonObject:
        return {
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "result": self.result,
            "error": self.error,
            "permissions": sorted(item.value for item in self.permissions),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ToolResult":
        return cls(
            str(data["tool_call_id"]),
            str(data["name"]),
            _json_safe(data.get("result")),
            data.get("error"),
            frozenset(ToolPermission(item) for item in data.get("permissions", ())),
        )


@dataclass(frozen=True, slots=True)
class ContentBlock:
    type: str
    data: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in CONTENT_BLOCK_TYPES:
            raise ValueError(f"unknown content block type: {self.type}")
        data = _obj(self.data)
        if self.type == "tool_use":
            if "tool_call" not in data:
                raise ValueError("tool_use content block requires data['tool_call']")
            data["tool_call"] = ToolCall.from_json(data["tool_call"]).to_json()
        if self.type == "tool_result":
            if "tool_result" not in data:
                raise ValueError("tool_result content block requires data['tool_result']")
            data["tool_result"] = ToolResult.from_json(data["tool_result"]).to_json()
        object.__setattr__(self, "data", data)

    def to_json(self) -> JsonObject:
        return {"type": self.type, **self.data}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ContentBlock":
        block = dict(data)
        return cls(str(block.pop("type")), block)


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: tuple[ContentBlock, ...] = field(default_factory=tuple)
    metadata: JsonObject = field(default_factory=dict)
    pinned: bool = False

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("Message role is required")
        if not isinstance(self.pinned, bool):
            raise ValueError("Message pinned must be bool")
        object.__setattr__(self, "content", tuple(self.content))
        object.__setattr__(self, "metadata", _obj(self.metadata))

    def to_json(self) -> JsonObject:
        return {
            "role": self.role,
            "content": [item.to_json() for item in self.content],
            "metadata": self.metadata,
            "pinned": self.pinned,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Message":
        return cls(
            str(data["role"]),
            _tuple(ContentBlock, data.get("content", ())),
            _obj(data.get("metadata")),
            data.get("pinned", False),
        )


def make_tool_result_block(result: ToolResult) -> ContentBlock:
    return ContentBlock("tool_result", {"tool_result": result.to_json()})


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    run_id: str
    seq: int
    timestamp: str
    type: str
    payload: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {self.type}")
        if self.seq < 0:
            raise ValueError("Event seq must be non-negative")
        payload = _obj(self.payload)
        if self.type == "error":
            _validate_error_payload(payload)
        elif self.type == "context_compressed":
            _validate_context_compressed_payload(payload)
        object.__setattr__(self, "payload", payload)

    def to_json(self) -> JsonObject:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "seq": self.seq,
            "timestamp": self.timestamp,
            "type": self.type,
            "payload": self.payload,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Event":
        return cls(
            str(data["event_id"]),
            str(data["run_id"]),
            int(data["seq"]),
            str(data["timestamp"]),
            str(data["type"]),
            _obj(data.get("payload")),
        )


@dataclass(frozen=True, slots=True)
class KernelConfig:
    max_steps: int = 20
    max_tool_calls: int = 20
    max_total_tokens: int | None = None
    timeout_seconds: float | None = None
    retry_max_attempts: int = 2
    retry_backoff_seconds: float = 1.0
    allow_parallel_tool_calls: bool = False

    def __post_init__(self) -> None:
        if min(self.max_steps, self.max_tool_calls, self.retry_max_attempts) < 0:
            raise ValueError("budgets and retry attempts must be non-negative")
        if self.max_total_tokens is not None and self.max_total_tokens < 0:
            raise ValueError("token budget must be non-negative")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry backoff must be non-negative")

    def to_json(self) -> JsonObject:
        return {
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "max_total_tokens": self.max_total_tokens,
            "timeout_seconds": self.timeout_seconds,
            "retry_max_attempts": self.retry_max_attempts,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "allow_parallel_tool_calls": self.allow_parallel_tool_calls,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "KernelConfig":
        return cls(**dict(data))


@dataclass(frozen=True, slots=True)
class ProviderResult:
    message: Message
    usage: JsonObject = field(default_factory=dict)
    finish_reason: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "usage", _obj(self.usage))
        object.__setattr__(self, "metadata", _obj(self.metadata))

    def to_json(self) -> JsonObject:
        return {
            "message": self.message.to_json(),
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ProviderResult":
        return cls(
            Message.from_json(data["message"]),
            _obj(data.get("usage")),
            data.get("finish_reason"),
            _obj(data.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class ProviderStreamEvent:
    type: str
    delta: JsonObject = field(default_factory=dict)
    usage: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "delta", _obj(self.delta))
        object.__setattr__(self, "usage", _obj(self.usage))
        object.__setattr__(self, "metadata", _obj(self.metadata))

    def to_json(self) -> JsonObject:
        return {
            "type": self.type,
            "delta": self.delta,
            "usage": self.usage,
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ProviderStreamEvent":
        return cls(
            str(data["type"]),
            _obj(data.get("delta")),
            _obj(data.get("usage")),
            _obj(data.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class AgentState:
    run_id: str | None = None
    status: RunStatus = RunStatus.RUNNING
    messages: tuple[Message, ...] = field(default_factory=tuple)
    steps_used: int = 0
    tool_calls_used: int = 0
    total_tokens_used: int = 0
    interrupted: bool = False
    last_seq: int = -1
    errors: tuple[JsonObject, ...] = field(default_factory=tuple)

    @classmethod
    def fold(cls, events: Sequence[Event]) -> "AgentState":
        state = cls()
        for event in sorted(events, key=lambda item: item.seq):
            payload = event.payload
            messages, errors = state.messages, state.errors
            status, interrupted = state.status, state.interrupted
            steps, calls, tokens = (
                state.steps_used,
                state.tool_calls_used,
                state.total_tokens_used,
            )
            if event.type == "message_added":
                messages += (Message.from_json(payload["message"]),)
            elif event.type == "budget_updated":
                budget = _required_ints(
                    payload,
                    ("used_steps", "max_steps", "used_tool_calls", "max_tool_calls"),
                )
                steps = budget["used_steps"]
                calls = budget["used_tool_calls"]
            elif event.type == "interrupted":
                interrupted = True
            elif event.type == "error":
                errors += (_obj(payload),)
            elif event.type == "run_finished":
                status = RunStatus(payload["status"])
            state = cls(
                event.run_id,
                status,
                messages,
                steps,
                calls,
                tokens,
                interrupted,
                event.seq,
                errors,
            )
        return state

    def to_json(self) -> JsonObject:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "messages": [item.to_json() for item in self.messages],
            "steps_used": self.steps_used,
            "tool_calls_used": self.tool_calls_used,
            "total_tokens_used": self.total_tokens_used,
            "interrupted": self.interrupted,
            "last_seq": self.last_seq,
            "errors": list(self.errors),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "AgentState":
        return cls(
            data.get("run_id"),
            RunStatus(data.get("status", RunStatus.RUNNING.value)),
            _tuple(Message, data.get("messages", ())),
            int(data.get("steps_used", 0)),
            int(data.get("tool_calls_used", 0)),
            int(data.get("total_tokens_used", 0)),
            bool(data.get("interrupted", False)),
            int(data.get("last_seq", -1)),
            tuple(_obj(item) for item in data.get("errors", ())),
        )


@dataclass(frozen=True, slots=True)
class RunResult:
    status: RunStatus
    state: AgentState
    events: tuple[Event, ...] = field(default_factory=tuple)
    reason: str | None = None
    output: Message | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.status.is_terminal:
            raise ValueError("RunResult status must be terminal")
        object.__setattr__(self, "events", tuple(self.events))
        run_finished = [event for event in self.events if event.type == "run_finished"]
        if run_finished and self.reason != run_finished[-1].payload.get("reason"):
            raise ValueError("RunResult.reason must match final run_finished reason")

    def to_json(self) -> JsonObject:
        return {
            "status": self.status.value,
            "state": self.state.to_json(),
            "events": [item.to_json() for item in self.events],
            "reason": self.reason,
            "output": None if self.output is None else self.output.to_json(),
            "error": self.error,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "RunResult":
        output = data.get("output")
        return cls(
            RunStatus(data["status"]),
            AgentState.from_json(data["state"]),
            _tuple(Event, data.get("events", ())),
            data.get("reason"),
            None if output is None else Message.from_json(output),
            data.get("error"),
        )


@dataclass(slots=True)
class MockProvider:
    """Deterministic provider test double for S2/S3 lifecycle tests."""

    script: Sequence[ProviderResult | ProviderStreamEvent | Exception | Mapping[str, Any]]
    supports_streaming: bool = False
    max_context: int | None = None
    calls: list[JsonObject] = field(default_factory=list)
    _index: int = 0

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]] | None = None,
    ) -> ProviderResult | ProviderStreamEvent:
        self.calls.append(
            {
                "messages": [message.to_json() for message in messages],
                "tools": [_obj(tool) for tool in (tools or ())],
            }
        )
        if self._index >= len(self.script):
            raise RuntimeError("MockProvider script exhausted")
        item = self.script[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, (ProviderResult, ProviderStreamEvent)):
            return item
        return ProviderResult.from_json(item) if item.get("message") else ProviderStreamEvent.from_json(item)
