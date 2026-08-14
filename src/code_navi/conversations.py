"""Minimal shared contracts for explicit business conversation recovery and context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from kernel.core import Message

ScopeT = TypeVar("ScopeT", contravariant=True)
StateT = TypeVar("StateT", covariant=True)
ContextInputT = TypeVar("ContextInputT", contravariant=True)
ContextOutputT = TypeVar("ContextOutputT", covariant=True)


class ConversationStateStore(Protocol[ScopeT, StateT]):
    """Load one explicit business conversation identifier within a Host-owned scope."""

    def load(self, conversation_id: str, scope: ScopeT) -> StateT: ...


class ContextAssembler(Protocol[ContextInputT, ContextOutputT]):
    """Build the provider-visible history for one Host request."""

    def assemble(self, context: ContextInputT) -> ContextOutputT: ...


@dataclass(frozen=True, slots=True)
class RecentTurnsContextInput:
    history: tuple[Message, ...]
    budget_tokens: int


class RecentTurnsContextAssembler:
    """Keep complete recent user/assistant turns inside a bounded window."""

    def assemble(self, context: RecentTurnsContextInput) -> tuple[Message, ...]:
        if context.budget_tokens < 1:
            raise ValueError("context budget must be positive")
        remaining = context.budget_tokens
        selected: list[Message] = []
        index = len(context.history)
        while index > 0:
            start = max(0, index - 2)
            turn = context.history[start:index]
            size = sum(
                len(str(block.data.get("text", "")))
                for message in turn
                for block in message.content
                if block.type == "text"
            )
            if size > remaining:
                break
            selected[0:0] = turn
            remaining -= size
            index = start
        return tuple(selected)


__all__ = [
    "ContextAssembler",
    "ConversationStateStore",
    "RecentTurnsContextAssembler",
    "RecentTurnsContextInput",
]
