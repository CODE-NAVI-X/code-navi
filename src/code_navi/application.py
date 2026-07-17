"""Application use case for context-aware code learning questions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from kernel.runtime import AgentRuntime, RuntimeRequest, RuntimeResult

from code_navi.assistant import code_learning_agent
from code_navi.context import (
    ContextBuilder,
    ContextSlice,
    ConversationTurn,
)


@dataclass(frozen=True, slots=True)
class QuestionResult:
    """Host-facing result for one context-aware question."""

    question: str
    context: ContextSlice
    runtime: RuntimeResult

    @property
    def output_text(self) -> str:
        return self.runtime.output_text or ""


class QuestionService:
    """Compose bounded context with the kernel's single-agent runtime."""

    def __init__(
        self,
        provider: object,
        context_builder: ContextBuilder,
        *,
        events_dir: str | Path,
        session_id: str | None = None,
    ) -> None:
        self.context_builder = context_builder
        self.session_id = session_id or f"cli-{uuid4()}"
        self.runtime = AgentRuntime(provider, session_dir=events_dir)

    def ask(
        self,
        question: str,
        *,
        attachments: tuple[str, ...] = (),
        last_answer: str | None = None,
        branch_history: tuple[ConversationTurn, ...] = (),
    ) -> QuestionResult:
        """Answer one question without mutating project files or task state."""
        prepared = self.context_builder.prepare(
            question,
            attachments=attachments,
            last_answer=last_answer,
            branch_history=branch_history,
        )
        result = self.runtime.run(
            code_learning_agent,
            RuntimeRequest(
                prepared.runtime_input(),
                session_id=self.session_id,
                metadata={
                    "interface": "cli",
                    "context_sources": list(prepared.context.sources),
                },
            ),
        )
        return QuestionResult(prepared.question, prepared.context, result)


__all__ = ["QuestionResult", "QuestionService"]
