"""Deterministic provider test double for contract and loop tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from kernel.core.provider import ProviderCapabilities, ProviderTool
from kernel.core.types import JsonObject, Message, ProviderResult


@dataclass(slots=True)
class MockProvider:
    script: Sequence[ProviderResult | Exception | Mapping[str, object]]
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    calls: list[JsonObject] = field(default_factory=list)
    _index: int = 0

    @property
    def max_context(self) -> int | None:
        return self.capabilities.max_context

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ProviderTool] = (),
    ) -> ProviderResult:
        self.calls.append(
            {
                "messages": [message.to_json() for message in messages],
                "tools": [tool.to_json() for tool in tools],
            }
        )
        if self._index >= len(self.script):
            raise RuntimeError("MockProvider script exhausted")
        item = self.script[self._index]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ProviderResult):
            return item
        return ProviderResult.from_json(item)
