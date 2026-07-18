"""Kernel-native provider contract shared by loops and adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from .types import Message, ProviderResult


def _json_object(value: Mapping[str, object]) -> dict[str, object]:
    try:
        encoded = json.dumps(dict(value))
    except (TypeError, ValueError) as exc:
        raise TypeError("value must be JSON-serializable") from exc
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("value must be a JSON object")
    return decoded


@dataclass(frozen=True, slots=True)
class ProviderTool:
    """Model-visible, provider-neutral tool description."""

    name: str
    description: str
    args_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ProviderTool name is required")
        if not self.description.strip():
            raise ValueError("ProviderTool description is required")
        schema = _json_object(self.args_schema)
        if schema.get("type") != "object":
            raise ValueError("ProviderTool args_schema root must have type 'object'")
        object.__setattr__(self, "args_schema", schema)

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "args_schema": _json_object(self.args_schema),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> ProviderTool:
        if frozenset(data) != {"name", "description", "args_schema"}:
            raise ValueError("ProviderTool requires exactly name, description, and args_schema")
        schema = data["args_schema"]
        if not isinstance(schema, Mapping):
            raise ValueError("ProviderTool args_schema must be an object")
        return cls(str(data["name"]), str(data["description"]), schema)


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Small, provider-neutral capability descriptor used by the kernel."""

    supports_streaming: bool = False
    supports_parallel_tool_calls: bool = False
    max_context: int | None = None
    unsupported_content_blocks: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.supports_streaming, bool):
            raise ValueError("supports_streaming must be bool")
        if not isinstance(self.supports_parallel_tool_calls, bool):
            raise ValueError("supports_parallel_tool_calls must be bool")
        if self.max_context is not None and self.max_context <= 0:
            raise ValueError("max_context must be None or positive")
        blocks = frozenset(str(item) for item in self.unsupported_content_blocks)
        object.__setattr__(self, "unsupported_content_blocks", blocks)

    def to_json(self) -> dict[str, object]:
        return {
            "supports_streaming": self.supports_streaming,
            "supports_parallel_tool_calls": self.supports_parallel_tool_calls,
            "max_context": self.max_context,
            "unsupported_content_blocks": sorted(self.unsupported_content_blocks),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> ProviderCapabilities:
        return cls(
            supports_streaming=data.get("supports_streaming", False),
            supports_parallel_tool_calls=data.get("supports_parallel_tool_calls", False),
            max_context=data.get("max_context"),
            unsupported_content_blocks=frozenset(
                str(item) for item in data.get("unsupported_content_blocks", ())
            ),
        )


class RetryableProviderError(Exception):
    """Provider failure that the S3 loop may retry within configured bounds."""


class FatalProviderError(Exception):
    """Provider failure that the S3 loop must not retry."""


class Provider(Protocol):
    """The single provider completion boundary owned by kernel core."""

    capabilities: ProviderCapabilities

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ProviderTool] = (),
    ) -> ProviderResult: ...
