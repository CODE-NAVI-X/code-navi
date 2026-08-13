"""Budgeted, persistence-aware context assembly for research conversations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from kernel.core import ContentBlock, Message

from .conversation_schemas import (
    ResearchContextSummary,
    ResearchConversationMessage,
)


def estimate_text_tokens(text: str) -> int:
    """Use a conservative dependency-free estimate suitable for mixed Chinese text."""
    return max(1, len(text))


def estimate_message_tokens(messages: tuple[Message, ...]) -> int:
    return sum(
        estimate_text_tokens(str(block.data.get("text", "")))
        for message in messages
        for block in message.content
        if block.type == "text"
    )


class ContextCompactor(Protocol):
    def compact(
        self,
        previous_summary: str | None,
        messages: tuple[ResearchConversationMessage, ...],
        budget_tokens: int,
    ) -> str: ...


class ConversationCompactor:
    """Create a bounded deterministic transcript summary without another model run."""

    def compact(
        self,
        previous_summary: str | None,
        messages: tuple[ResearchConversationMessage, ...],
        budget_tokens: int,
    ) -> str:
        if budget_tokens < 1:
            raise ValueError("summary budget must be positive")
        parts = []
        if previous_summary:
            parts.append(f"既有摘要：{previous_summary}")
        parts.extend(
            f"{'用户' if message.role == 'user' else '助手'}：{message.content}"
            for message in messages
        )
        summary = "\n".join(parts).strip()
        if not summary:
            raise ValueError("summary source messages must not be empty")
        if budget_tokens < len(parts) * 2:
            raise ValueError("summary budget cannot represent every source segment")
        per_part = max(1, (budget_tokens - len(parts) + 1) // len(parts))
        return "\n".join(part[:per_part] for part in parts)[:budget_tokens]


@dataclass(frozen=True, slots=True)
class ContextAssembly:
    conversation_history: tuple[Message, ...]
    token_count: int
    pending_summary: ResearchContextSummary | None = None


@dataclass(frozen=True, slots=True)
class ResearchContextInput:
    messages: list[ResearchConversationMessage]
    system_prompt: str
    runtime_input: str
    persisted_summary: ResearchContextSummary | None


class ResearchContextAssembler:
    """Reuse a persisted summary and compact only uncovered oldest messages."""

    def __init__(
        self,
        *,
        budget_tokens: int = 16_000,
        summary_budget_tokens: int = 2_000,
        compactor: ContextCompactor | None = None,
    ) -> None:
        if budget_tokens < 1 or summary_budget_tokens < 1:
            raise ValueError("context budgets must be positive")
        self.budget_tokens = budget_tokens
        self.summary_budget_tokens = summary_budget_tokens
        self.compactor = compactor or ConversationCompactor()

    def assemble(self, context: ResearchContextInput) -> ContextAssembly:
        uncovered = self._uncovered_messages(
            context.messages,
            context.persisted_summary,
        )
        fixed_tokens = sum(
            estimate_text_tokens(value)
            for value in (
                context.system_prompt,
                context.runtime_input,
            )
        )
        history = self._history(context.persisted_summary, uncovered)
        total = fixed_tokens + estimate_message_tokens(history)
        if total <= self.budget_tokens:
            return ContextAssembly(history, total)
        available = self.budget_tokens - fixed_tokens
        if available < 2:
            raise ValueError("pinned research context exceeds the configured budget")

        summary_budget = min(self.summary_budget_tokens, max(1, available // 2))
        tail: list[ResearchConversationMessage] = []
        tail_tokens = 0
        for message in reversed(uncovered):
            message_tokens = estimate_text_tokens(message.content)
            if tail_tokens + message_tokens + summary_budget > available:
                break
            tail.insert(0, message)
            tail_tokens += message_tokens
        sources = tuple(uncovered[: len(uncovered) - len(tail)])
        if not sources:
            sources = tuple(uncovered)
            tail = []
            tail_tokens = 0
        if not sources:
            raise ValueError("persisted summary and pinned context exceed the configured budget")
        summary_budget = min(summary_budget, available - tail_tokens)
        summary_text = self.compactor.compact(
            context.persisted_summary.summary if context.persisted_summary else None,
            sources,
            summary_budget,
        )
        pending = ResearchContextSummary(
            summary=summary_text,
            through_message_id=sources[-1].message_id,
            source_message_count=(
                (
                    context.persisted_summary.source_message_count
                    if context.persisted_summary
                    else 0
                )
                + len(sources)
            ),
            generation_mode="rules",
            run_id=f"context-summary-{uuid4()}",
        )
        compacted_history = self._history(pending, tail)
        total = fixed_tokens + estimate_message_tokens(compacted_history)
        if total > self.budget_tokens:
            raise ValueError("assembled research context exceeds the configured budget")
        return ContextAssembly(compacted_history, total, pending)

    @staticmethod
    def _uncovered_messages(
        messages: list[ResearchConversationMessage],
        summary: ResearchContextSummary | None,
    ) -> list[ResearchConversationMessage]:
        if summary is None:
            return messages
        for index, message in enumerate(messages):
            if message.message_id == summary.through_message_id:
                return messages[index + 1 :]
        raise ValueError("persisted summary boundary is not present in conversation history")

    @staticmethod
    def _history(
        summary: ResearchContextSummary | None,
        messages: list[ResearchConversationMessage],
    ) -> tuple[Message, ...]:
        history: list[Message] = []
        if summary is not None:
            history.append(
                Message(
                    "system",
                    (ContentBlock("text", {"text": summary.summary}),),
                    {
                        "context_kind": "research_conversation_summary",
                        "through_message_id": summary.through_message_id,
                    },
                )
            )
        history.extend(
            Message(
                message.role,
                (ContentBlock("text", {"text": message.content}),),
                {
                    "message_id": message.message_id,
                    "created_at": message.created_at.isoformat(),
                },
            )
            for message in messages
        )
        return tuple(history)
