"""Business persistence and orchestration for resumable CLI shell conversations."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Column, DateTime, String
from sqlalchemy.orm import Session, sessionmaker

from code_navi.conversations import ConversationStateStore
from code_navi.db import Base
from kernel.core import ContentBlock, Message

from .application import QuestionResult, QuestionService
from .context import ConversationTurn


class CliConversationNotFoundError(LookupError):
    """Raised when an explicitly requested CLI conversation does not exist."""


class CliConversationScopeError(LookupError):
    """Raised when a CLI conversation belongs to a different project root."""


class CliConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message_id: str = Field(min_length=1)
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=20_000)
    created_at: datetime


class CliConversationModel(Base):
    """One project-scoped, explicitly resumable CLI shell main conversation."""

    __tablename__ = "cli_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_scope = Column(String(2000), nullable=False, index=True)
    messages_data = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


@dataclass(frozen=True, slots=True)
class CliConversationState:
    conversation_id: str
    project_scope: str
    messages: tuple[CliConversationMessage, ...]

    @property
    def last_answer(self) -> str | None:
        return next(
            (message.content for message in reversed(self.messages) if message.role == "assistant"),
            None,
        )

    def kernel_history(self) -> tuple[Message, ...]:
        return tuple(
            Message(
                message.role,
                (ContentBlock("text", {"text": message.content}),),
                {"message_id": message.message_id},
            )
            for message in self.messages
        )


def project_scope(project_root: str | Path) -> str:
    resolved = str(Path(project_root).expanduser().resolve(strict=False))
    return os.path.normcase(resolved)


class CliConversationStateStore(
    ConversationStateStore[str | Path, CliConversationState],
    Protocol,
):
    def create(self, project_root: str | Path) -> CliConversationState: ...

    def append_turn(
        self,
        conversation_id: str,
        project_root: str | Path,
        user_message: str,
        assistant_message: str,
    ) -> CliConversationState: ...


class CliConversationStore:
    """SQLAlchemy store for CLI-only business conversation state."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, project_root: str | Path) -> CliConversationState:
        with self._session_factory() as db:
            model = CliConversationModel(
                project_scope=project_scope(project_root),
                messages_data=[],
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._state(model)

    def load(self, conversation_id: str, project_root: str | Path) -> CliConversationState:
        with self._session_factory() as db:
            model = db.get(CliConversationModel, conversation_id)
            if model is None:
                raise CliConversationNotFoundError(conversation_id)
            if model.project_scope != project_scope(project_root):
                raise CliConversationScopeError(conversation_id)
            return self._state(model)

    def append_turn(
        self,
        conversation_id: str,
        project_root: str | Path,
        user_message: str,
        assistant_message: str,
    ) -> CliConversationState:
        with self._session_factory() as db:
            model = db.get(CliConversationModel, conversation_id)
            if model is None:
                raise CliConversationNotFoundError(conversation_id)
            if model.project_scope != project_scope(project_root):
                raise CliConversationScopeError(conversation_id)
            now = datetime.now(UTC)
            additions = (
                CliConversationMessage(
                    message_id=str(uuid.uuid4()),
                    role="user",
                    content=user_message,
                    created_at=now,
                ),
                CliConversationMessage(
                    message_id=str(uuid.uuid4()),
                    role="assistant",
                    content=assistant_message,
                    created_at=now,
                ),
            )
            model.messages_data = [
                *model.messages_data,
                *(message.model_dump(mode="json") for message in additions),
            ]
            db.commit()
            db.refresh(model)
            return self._state(model)

    @staticmethod
    def _state(model: CliConversationModel) -> CliConversationState:
        return CliConversationState(
            model.id,
            model.project_scope,
            tuple(CliConversationMessage.model_validate(item) for item in model.messages_data),
        )


class ShellConversationService:
    """Run and persist only the CLI shell's main conversation."""

    def __init__(
        self,
        question_service: QuestionService,
        store: CliConversationStateStore,
        state: CliConversationState,
    ) -> None:
        self.question_service = question_service
        self.store = store
        self.state = state

    @property
    def conversation_id(self) -> str:
        return self.state.conversation_id

    @property
    def last_answer(self) -> str | None:
        return self.state.last_answer

    def ask_main(self, question: str) -> QuestionResult:
        result = self.question_service.ask(
            question,
            conversation_history=self.state.kernel_history(),
        )
        if result.output_text:
            self.state = self.store.append_turn(
                self.state.conversation_id,
                self.question_service.context_builder.project_root,
                result.question,
                result.output_text,
            )
        return result

    def ask_branch(
        self,
        question: str,
        *,
        last_answer: str | None,
        branch_history: tuple[ConversationTurn, ...],
    ) -> QuestionResult:
        return self.question_service.ask(
            question,
            last_answer=last_answer,
            branch_history=branch_history,
            conversation_history=self.state.kernel_history(),
        )


__all__ = [
    "CliConversationModel",
    "CliConversationNotFoundError",
    "CliConversationScopeError",
    "CliConversationState",
    "CliConversationStore",
    "ShellConversationService",
]
