"""DeepSeek Chat Completions adapter for the Kernel provider contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import openai

from kernel.core import (
    ContentBlock,
    FatalProviderError,
    Message,
    ProviderCapabilities,
    ProviderResult,
    ProviderTool,
    RetryableProviderError,
)


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


class DeepSeekChatCompletionsAdapter:
    """Translate Kernel text messages to DeepSeek Chat Completions."""

    def __init__(
        self,
        model: str,
        *,
        client: Any,
        max_output_tokens: int | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model is required")
        if max_output_tokens is not None and max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be None or positive")
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.capabilities = ProviderCapabilities(
            supports_streaming=False,
            supports_parallel_tool_calls=False,
            unsupported_content_blocks=frozenset(
                {"tool_use", "tool_result", "image_ref", "artifact_ref"}
            ),
        )
        self._client = client

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ProviderTool] = (),
    ) -> ProviderResult:
        """Request one JSON response and convert it to a Kernel result."""

        if tools:
            raise FatalProviderError("DeepSeek evaluator does not expose tools")
        request: dict[str, Any] = {
            "model": self.model,
            "messages": self._chat_messages(messages),
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        if self.max_output_tokens is not None:
            request["max_tokens"] = self.max_output_tokens
        try:
            response = self._client.chat.completions.create(**request)
        except openai.APIError as exc:
            self._raise_mapped_error(exc)
        return self._provider_result(response)

    @staticmethod
    def _chat_messages(messages: Sequence[Message]) -> list[dict[str, str]]:
        chat_messages: list[dict[str, str]] = []
        for message in messages:
            if message.role not in {"system", "developer", "user", "assistant"}:
                raise FatalProviderError(
                    f"DeepSeek Chat Completions does not support role {message.role!r}"
                )
            parts: list[str] = []
            for block in message.content:
                if block.type != "text":
                    raise FatalProviderError(
                        f"DeepSeek evaluator does not support {block.type} content blocks"
                    )
                value = block.data.get("text")
                if not isinstance(value, str):
                    raise FatalProviderError("text content block requires string text")
                parts.append(value)
            role = "system" if message.role == "developer" else message.role
            chat_messages.append({"role": role, "content": "\n".join(parts)})
        return chat_messages

    def _provider_result(self, response: Any) -> ProviderResult:
        choices = _value(response, "choices", ())
        if not choices:
            raise FatalProviderError("DeepSeek returned no completion choices")
        choice = choices[0]
        message = _value(choice, "message")
        content = _value(message, "content")
        if not isinstance(content, str) or not content.strip():
            raise FatalProviderError("DeepSeek returned empty message content")

        usage = _value(response, "usage")
        normalized_usage: dict[str, Any] = {}
        if usage is not None:
            for source, target in (
                ("prompt_tokens", "input_tokens"),
                ("completion_tokens", "output_tokens"),
                ("total_tokens", "total_tokens"),
            ):
                value = _value(usage, source)
                if value is not None:
                    normalized_usage[target] = value

        finish_reason = _value(choice, "finish_reason")
        return ProviderResult(
            Message("assistant", (ContentBlock("text", {"text": content}),)),
            usage=normalized_usage,
            finish_reason=None if finish_reason is None else str(finish_reason),
            metadata={
                "provider": "deepseek",
                "response_id": _value(response, "id"),
                "model": _value(response, "model", self.model),
                "request_id": _value(response, "_request_id"),
            },
        )

    @staticmethod
    def _raise_mapped_error(exc: openai.APIError) -> None:
        status = getattr(exc, "status_code", None)
        retryable = isinstance(
            exc, (openai.APIConnectionError, openai.APITimeoutError)
        ) or status in {408, 409, 429} or (isinstance(status, int) and status >= 500)
        if retryable:
            raise RetryableProviderError(str(exc)) from exc
        raise FatalProviderError(str(exc)) from exc
