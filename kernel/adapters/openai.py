"""OpenAI Responses API translation layer for the kernel Provider contract."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

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


class OpenAIResponsesAdapter:
    """Translate kernel-native messages and tools to the OpenAI Responses API."""

    def __init__(
        self,
        model: str,
        *,
        client: Any | None = None,
        max_output_tokens: int | None = None,
        max_context: int | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model is required")
        if max_output_tokens is not None and max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be None or positive")
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.capabilities = ProviderCapabilities(
            supports_streaming=False,
            supports_parallel_tool_calls=True,
            max_context=max_context,
            unsupported_content_blocks=frozenset({"image_ref", "artifact_ref"}),
        )
        self._client = (
            openai.OpenAI(max_retries=0)
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
            "input": self._input_items(messages),
            "tools": [self._native_tool(tool) for tool in tools],
            "store": False,
        }
        if self.max_output_tokens is not None:
            request["max_output_tokens"] = self.max_output_tokens
        try:
            response = self._client.responses.create(**request)
        except openai.APIError as exc:
            self._raise_mapped_error(exc)
        return self._provider_result(response)

    @staticmethod
    def _native_tool(tool: ProviderTool) -> dict[str, Any]:
        schema = tool.to_json()["args_schema"]
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": schema,
            "strict": False,
        }

    def _input_items(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if message.role not in {"system", "developer", "user", "assistant", "tool"}:
                raise FatalProviderError(
                    f"OpenAI Responses does not support message role {message.role!r}"
                )
            if not message.content:
                if message.role == "tool":
                    raise FatalProviderError("tool messages require a tool_result block")
                items.append({"role": message.role, "content": ""})
                continue
            for block in message.content:
                if block.type == "text":
                    if message.role == "tool":
                        raise FatalProviderError(
                            "OpenAI tool messages cannot contain text blocks"
                        )
                    text = block.data.get("text")
                    if not isinstance(text, str):
                        raise FatalProviderError("text content block requires string text")
                    items.append({"role": message.role, "content": text})
                    continue
                if block.type == "tool_use":
                    call = ToolCall.from_json(block.data["tool_call"])
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call.id,
                            "name": call.name,
                            "arguments": json.dumps(
                                call.args, ensure_ascii=False, separators=(",", ":")
                            ),
                        }
                    )
                    continue
                if block.type == "tool_result":
                    result = ToolResult.from_json(block.data["tool_result"])
                    items.append(
                        {
                            "type": "function_call_output",
                            "call_id": result.tool_call_id,
                            "output": json.dumps(
                                {"result": result.result, "error": result.error},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                    )
                    continue
                raise FatalProviderError(
                    f"OpenAI Responses does not support {block.type} content blocks"
                )
        return items

    def _provider_result(self, response: Any) -> ProviderResult:
        blocks: list[ContentBlock] = []
        output_types: list[str] = []
        for item in _value(response, "output", ()):
            item_type = str(_value(item, "type", ""))
            output_types.append(item_type)
            if item_type == "reasoning":
                continue
            if item_type == "function_call":
                blocks.append(self._tool_use_block(item))
                continue
            if item_type == "message":
                blocks.extend(self._text_blocks(item))
                continue
            raise FatalProviderError(
                f"OpenAI Responses returned unsupported output item {item_type!r}"
            )

        usage = _value(response, "usage")
        normalized_usage: dict[str, Any] = {}
        if usage is not None:
            for source, target in (
                ("input_tokens", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("total_tokens", "total_tokens"),
            ):
                value = _value(usage, source)
                if value is not None:
                    normalized_usage[target] = value
        status = _value(response, "status")
        finish_reason = "tool_use" if any(
            block.type == "tool_use" for block in blocks
        ) else (None if status is None else str(status))
        metadata = {
            "provider": "openai",
            "response_id": _value(response, "id"),
            "model": _value(response, "model", self.model),
            "request_id": _value(response, "_request_id"),
            "output_types": output_types,
        }
        return ProviderResult(
            Message("assistant", tuple(blocks)),
            usage=normalized_usage,
            finish_reason=finish_reason,
            metadata=metadata,
        )

    @staticmethod
    def _tool_use_block(item: Any) -> ContentBlock:
        arguments = _value(item, "arguments")
        try:
            args = json.loads(arguments)
        except (TypeError, ValueError) as exc:
            raise FatalProviderError(
                "OpenAI function call arguments are not valid JSON"
            ) from exc
        if not isinstance(args, dict):
            raise FatalProviderError("OpenAI function call arguments must be an object")
        call_id = _value(item, "call_id")
        name = _value(item, "name")
        if not isinstance(call_id, str) or not isinstance(name, str):
            raise FatalProviderError("OpenAI function call lacks call_id or name")
        call = ToolCall(call_id, name, args)
        return ContentBlock("tool_use", {"tool_call": call.to_json()})

    @staticmethod
    def _text_blocks(item: Any) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        for content in _value(item, "content", ()):
            content_type = _value(content, "type")
            if content_type == "output_text":
                text = _value(content, "text")
            elif content_type == "refusal":
                text = _value(content, "refusal")
            else:
                raise FatalProviderError(
                    "OpenAI message returned unsupported content "
                    f"{content_type!r}"
                )
            if not isinstance(text, str):
                raise FatalProviderError("OpenAI message content must be text")
            blocks.append(ContentBlock("text", {"text": text}))
        return blocks

    @staticmethod
    def _raise_mapped_error(exc: openai.APIError) -> None:
        status = getattr(exc, "status_code", None)
        retryable = isinstance(
            exc, (openai.APIConnectionError, openai.APITimeoutError)
        ) or status in {408, 409, 429} or (
            isinstance(status, int) and status >= 500
        )
        if retryable:
            raise RetryableProviderError(str(exc)) from exc
        raise FatalProviderError(str(exc)) from exc
