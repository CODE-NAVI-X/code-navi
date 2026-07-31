"""Guarded provider-backed wording for the rules-owned research workflow."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Thread
from types import SimpleNamespace
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from code_navi.providers import ProviderConfigurationError, ProviderSettings, create_provider
from kernel.core import ContentBlock, Message

from .schemas import ClarificationQuestion, ResearchState

try:
    from openai import OpenAI
except ModuleNotFoundError:  # The server extra is intentionally optional for offline mode.
    OpenAI = None  # type: ignore[assignment,misc]


DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"


class LlmGuidance(BaseModel):
    """The only JSON shape accepted from a configured model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    reply: str = Field(min_length=1, max_length=500)
    next_question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=3, max_length=3)
    suggested_value: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_text(self) -> LlmGuidance:
        fields = [self.reply, self.next_question, *self.options]
        if any(not value.strip() for value in fields):
            raise ValueError("guidance text must not be blank")
        if len({value.strip() for value in self.options}) != 3:
            raise ValueError("guidance options must be distinct")
        if self.suggested_value is not None and not self.suggested_value.strip():
            raise ValueError("suggested_value must be non-blank when present")
        return self


@dataclass(frozen=True)
class GuidanceOutcome:
    """A safe result that distinguishes unavailable configuration from a failed call."""

    status: Literal["generated", "unavailable", "failed"]
    guidance: LlmGuidance | None = None
    reason: str | None = None

    @classmethod
    def generated(cls, guidance: LlmGuidance) -> GuidanceOutcome:
        return cls("generated", guidance)

    @classmethod
    def unavailable(cls) -> GuidanceOutcome:
        return cls("unavailable")

    @classmethod
    def failed(cls, reason: str) -> GuidanceOutcome:
        return cls("failed", reason=reason)


class GuidanceGenerator(Protocol):
    def generate(
        self,
        *,
        state: ResearchState,
        user_reply: str,
        target_question: ClarificationQuestion | None,
        requesting_suggestion: bool,
        suggestion_question: ClarificationQuestion | None = None,
    ) -> GuidanceOutcome: ...


class DeepSeekGuidanceProvider:
    """Research-only adapter for DeepSeek's OpenAI-compatible chat/completions API."""

    def __init__(self, client: object | None = None) -> None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ProviderConfigurationError("DeepSeek research guidance requires DEEPSEEK_API_KEY")
        if client is None and OpenAI is None:
            raise ProviderConfigurationError(
                'DeepSeek support is not installed; run pip install -e ".[server]"'
            )
        self.model = os.getenv("DEEPSEEK_MODEL", DEEPSEEK_DEFAULT_MODEL)
        self.client = client or OpenAI(  # type: ignore[operator]
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_DEFAULT_BASE_URL),
            max_retries=0,
        )

    def complete(self, messages: tuple[Message, ...]) -> object:
        response = self.client.chat.completions.create(  # type: ignore[attr-defined]
            model=self.model,
            messages=[self._message_payload(message) for message in messages],
            temperature=0.2,
            max_tokens=900,
        )
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as error:
            raise ValueError("DeepSeek response did not contain a message") from error
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek response did not contain text")
        return SimpleNamespace(
            message=Message("assistant", (ContentBlock("text", {"text": content}),))
        )

    @staticmethod
    def _message_payload(message: Message) -> dict[str, str]:
        if message.role not in {"system", "user", "assistant"}:
            raise ProviderConfigurationError(
                f"DeepSeek chat provider does not support message role {message.role!r}"
            )
        parts: list[str] = []
        for block in message.content:
            if block.type != "text" or not isinstance(block.data.get("text"), str):
                raise ProviderConfigurationError("DeepSeek messages must contain text only")
            parts.append(block.data["text"])
        return {"role": message.role, "content": "\n".join(parts)}


class ProviderGuidanceGenerator:
    """Uses the existing Provider configuration without adding a second key path."""

    def __init__(self, timeout_seconds: float = 8.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        state: ResearchState,
        user_reply: str,
        target_question: ClarificationQuestion | None,
        requesting_suggestion: bool,
        suggestion_question: ClarificationQuestion | None = None,
    ) -> GuidanceOutcome:
        settings = ProviderSettings.resolve()
        if settings.name == "deepseek" and not os.getenv("DEEPSEEK_API_KEY"):
            return GuidanceOutcome.unavailable()
        if settings.name == "openai" and not os.getenv("OPENAI_API_KEY"):
            return GuidanceOutcome.unavailable()
        if settings.name not in {"deepseek", "openai"}:
            return GuidanceOutcome.unavailable()
        try:
            provider = (
                DeepSeekGuidanceProvider()
                if settings.name == "deepseek"
                else create_provider(settings)
            )
            result = self._complete_with_timeout(
                provider,
                (
                    self._message(
                        state,
                        user_reply,
                        target_question,
                        requesting_suggestion,
                        suggestion_question,
                    ),
                ),
            )
            guidance = LlmGuidance.model_validate_json(self._text(result.message))
            if guidance.suggested_value is not None and not requesting_suggestion:
                raise ValueError("suggested_value is only allowed for a recommendation request")
            return GuidanceOutcome.generated(guidance)
        except (
            ProviderConfigurationError,
            TimeoutError,
            ValueError,
        ) as error:
            return GuidanceOutcome.failed(str(error))
        except (
            Exception
        ) as error:  # Provider SDK/network exceptions must never interrupt a session.
            return GuidanceOutcome.failed(str(error))

    def _complete_with_timeout(self, provider: object, messages: tuple[Message, ...]) -> object:
        """Bound a provider call without changing the shared kernel adapter contract."""
        results: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def complete() -> None:
            try:
                results.put((True, provider.complete(messages)))  # type: ignore[attr-defined]
            except Exception as error:
                results.put((False, error))

        Thread(target=complete, daemon=True).start()
        try:
            succeeded, value = results.get(timeout=self.timeout_seconds)
        except Empty as error:
            raise TimeoutError("research guidance provider timed out") from error
        if succeeded:
            return value
        if isinstance(value, Exception):
            raise value
        raise RuntimeError("provider call failed without an exception")

    @staticmethod
    def _text(message: Message) -> str:
        for block in message.content:
            if block.type == "text" and isinstance(block.data.get("text"), str):
                return block.data["text"]
        raise ValueError("provider response did not contain text")

    @staticmethod
    def _message(
        state: ResearchState,
        user_reply: str,
        target_question: ClarificationQuestion | None,
        requesting_suggestion: bool,
        suggestion_question: ClarificationQuestion | None,
    ) -> Message:
        target_context = target_question.model_dump() if target_question else None
        suggestion_context = suggestion_question.model_dump() if suggestion_question else None
        prompt = {
            "role": "科研澄清文案助手",
            "rules": [
                "只能生成 JSON，不要 Markdown 或额外字段。",
                "字段顺序、字段名、完成条件由后端规则决定，不能改变。",
                "next_question 和 options 只为后端提供的下一字段生成；options 必须恰好 3 条。",
                "reply 必须简短、具体，且不能把推测写成论文事实。",
                "仅当用户明确请求推荐时才可提供 suggested_value，且它必须填补该请求中的当前字段。",
            ],
            "state": state.model_dump(),
            "latest_user_reply": user_reply,
            "requesting_suggestion": requesting_suggestion,
            "suggestion_field": suggestion_context,
            "next_rule_question": target_context,
            "json_shape": {
                "reply": "string",
                "next_question": "string",
                "options": ["string", "string", "string"],
                "suggested_value": "string or null",
            },
        }
        return Message(
            "user", (ContentBlock("text", {"text": json.dumps(prompt, ensure_ascii=False)}),)
        )
