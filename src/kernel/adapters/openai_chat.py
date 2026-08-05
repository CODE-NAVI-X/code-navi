"""OpenAI-compatible Chat Completions adapter for internal runtime providers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import openai

from kernel.core.provider import (
    FatalProviderError,
    ProviderCapabilities,
    ProviderTool,
    RetryableProviderError,
)
from kernel.core.types import (
    ContentBlock,
    Message,
    ProviderResult,
    ToolCall,
    ToolResult,
)


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


class OpenAIChatCompletionsAdapter:
    """Translate runtime messages to OpenAI-compatible Chat Completions."""

    def __init__(
        self,
        model: str,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        provider_name: str = "openai_chat",
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        max_context: int | None = None,
        thinking: Literal["enabled", "disabled"] | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model is required")
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError("max_tokens must be None or positive")
        if temperature is not None and not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be None or within [0.0, 2.0]")
        if thinking not in {None, "enabled", "disabled"}:
            raise ValueError("thinking must be None, 'enabled' or 'disabled'")
        self.model = model
        self.provider_name = provider_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking = thinking
        self.capabilities = ProviderCapabilities(
            supports_streaming=False,
            supports_parallel_tool_calls=True,
            max_context=max_context,
            unsupported_content_blocks=frozenset({"image_ref", "artifact_ref"}),
        )
        self._client = (
            openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
                max_retries=0,
                **({} if timeout is None else {"timeout": timeout}),
            )
            if client is None
            else client.with_options(max_retries=0)
        )

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ProviderTool] = (),
    ) -> ProviderResult:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [self._native_message(message) for message in messages],
        }
        if tools:
            request["tools"] = [self._native_tool(tool) for tool in tools]
        if self.max_tokens is not None:
            request["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            request["temperature"] = self.temperature
        if self.thinking:
            # Reasoning models burn their token budget on chain-of-thought; for
            # structured JSON generation we opt out so content returns directly.
            request["extra_body"] = {"thinking": {"type": self.thinking}}
        try:
            response = self._client.chat.completions.create(**request)
        except openai.APIError as exc:
            self._raise_mapped_error(exc)
        return self._provider_result(response)

    @staticmethod
    def _native_tool(tool: ProviderTool) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.to_json()["args_schema"],
            },
        }

    @staticmethod
    def _native_message(message: Message) -> dict[str, Any]:
        role = "system" if message.role == "developer" else message.role
        if role not in {"system", "user", "assistant", "tool"}:
            raise FatalProviderError(
                f"Chat Completions does not support message role {message.role!r}"
            )
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_result: ToolResult | None = None
        for block in message.content:
            if block.type == "text":
                text = block.data.get("text")
                if not isinstance(text, str):
                    raise FatalProviderError("text content block requires string text")
                text_parts.append(text)
                continue
            if block.type == "tool_use":
                call = ToolCall.from_json(block.data["tool_call"])
                tool_calls.append(
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.args, ensure_ascii=False, separators=(",", ":")
                            ),
                        },
                    }
                )
                continue
            if block.type == "tool_result":
                tool_result = ToolResult.from_json(block.data["tool_result"])
                continue
            raise FatalProviderError(
                f"Chat Completions does not support {block.type} content blocks"
            )

        if role == "tool":
            if tool_result is None:
                raise FatalProviderError("tool messages require a tool_result block")
            return {
                "role": "tool",
                "tool_call_id": tool_result.tool_call_id,
                "content": json.dumps(
                    {"result": tool_result.result, "error": tool_result.error},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        native: dict[str, Any] = {"role": role, "content": "\n".join(text_parts)}
        if tool_calls:
            native["tool_calls"] = tool_calls
            if not text_parts:
                native["content"] = None
        return native

    def _provider_result(self, response: Any) -> ProviderResult:
        choices = tuple(_value(response, "choices", ()))
        if not choices:
            raise FatalProviderError("Chat Completions returned no choices")
        choice = choices[0]
        message = _value(choice, "message")
        if message is None:
            raise FatalProviderError("Chat Completions choice lacks message")

        blocks: list[ContentBlock] = []
        content = _value(message, "content")
        if isinstance(content, str) and content:
            blocks.append(ContentBlock("text", {"text": content}))
        for native_call in _value(message, "tool_calls", ()) or ():
            function = _value(native_call, "function")
            arguments = _value(function, "arguments")
            try:
                args = json.loads(arguments or "{}")
            except (TypeError, ValueError) as exc:
                raise FatalProviderError("Chat function call arguments are not valid JSON") from exc
            if not isinstance(args, dict):
                raise FatalProviderError("Chat function call arguments must be an object")
            call_id = _value(native_call, "id")
            name = _value(function, "name")
            if not isinstance(call_id, str) or not isinstance(name, str):
                raise FatalProviderError("Chat function call lacks id or name")
            blocks.append(
                ContentBlock("tool_use", {"tool_call": ToolCall(call_id, name, args).to_json()})
            )

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
        metadata = {
            "provider": self.provider_name,
            "response_id": _value(response, "id"),
            "model": _value(response, "model", self.model),
            "request_id": _value(response, "_request_id"),
        }
        return ProviderResult(
            Message("assistant", tuple(blocks)),
            usage=normalized_usage,
            finish_reason=None if finish_reason is None else str(finish_reason),
            metadata=metadata,
        )

    @staticmethod
    def _raise_mapped_error(exc: openai.APIError) -> None:
        status = getattr(exc, "status_code", None)
        retryable = (
            isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError))
            or status in {408, 409, 429}
            or (isinstance(status, int) and status >= 500)
        )
        if retryable:
            raise RetryableProviderError(str(exc)) from exc
        raise FatalProviderError(str(exc)) from exc
