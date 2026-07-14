from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

try:
    import httpx
    import openai

    from kernel.adapters.openai import OpenAIResponsesAdapter
except ModuleNotFoundError:
    httpx = None
    openai = None
    OpenAIResponsesAdapter = None
from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    Provider,
    ProviderCapabilities,
    ProviderResult,
    ProviderTool,
    RetryableProviderError,
    ToolCall,
    ToolResult,
    run,
)
from kernel.providers import MockProvider


ScriptItem = ProviderResult | Exception


@dataclass(frozen=True, slots=True)
class ProviderCase:
    name: str
    build: Callable[[Sequence[ScriptItem]], Provider]
    retryable_error: Callable[[], Exception]


def build_mock(script: Sequence[ScriptItem]) -> MockProvider:
    return MockProvider(
        tuple(script),
        capabilities=ProviderCapabilities(supports_parallel_tool_calls=True),
    )


class RecordedResponses:
    def __init__(self, script: Sequence[object]) -> None:
        self._script = list(script)

    def create(self, **request):
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RecordedClient:
    def __init__(self, script: Sequence[object]) -> None:
        self.responses = RecordedResponses(script)

    def with_options(self, **options):
        assert options == {"max_retries": 0}
        return self


def native_response(result: ProviderResult):
    output = []
    for block in result.message.content:
        if block.type == "text":
            output.append(
                SimpleNamespace(
                    type="message",
                    content=(
                        SimpleNamespace(
                            type="output_text", text=block.data["text"]
                        ),
                    ),
                )
            )
        elif block.type == "tool_use":
            call = ToolCall.from_json(block.data["tool_call"])
            output.append(
                SimpleNamespace(
                    type="function_call",
                    call_id=call.id,
                    name=call.name,
                    arguments=json.dumps(call.args),
                )
            )
        else:
            raise AssertionError(f"unsupported recorded block: {block.type}")
    return SimpleNamespace(
        id="recorded-response",
        model="recorded-model",
        status="completed",
        _request_id="recorded-request",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
        output=tuple(output),
    )


def build_recorded_openai(script: Sequence[ScriptItem]) -> OpenAIResponsesAdapter:
    assert OpenAIResponsesAdapter is not None
    native_script = [
        native_response(item) if isinstance(item, ProviderResult) else item
        for item in script
    ]
    return OpenAIResponsesAdapter(
        "recorded-model", client=RecordedClient(native_script)
    )


def recorded_rate_limit() -> openai.RateLimitError:
    assert httpx is not None and openai is not None
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError(
        "rate limited", response=response, body={"error": "recorded"}
    )


_provider_cases = [
    ProviderCase("mock", build_mock, lambda: RetryableProviderError("rate limited"))
]
if openai is not None:
    _provider_cases.append(
        ProviderCase("openai-recorded", build_recorded_openai, recorded_rate_limit)
    )
PROVIDER_CASES = tuple(_provider_cases)


def text_message(text: str, *, role: str = "assistant") -> Message:
    return Message(role, (ContentBlock("text", {"text": text}),))


def tool_message(*calls: ToolCall) -> Message:
    return Message(
        "assistant",
        tuple(
            ContentBlock("tool_use", {"tool_call": call.to_json()})
            for call in calls
        ),
    )


class ConformanceDispatcher:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []
        self._tools = (
            ProviderTool(
                "lookup",
                "Look up a deterministic local value.",
                {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            ),
        )

    def provider_tools(self) -> tuple[ProviderTool, ...]:
        return self._tools

    def dispatch(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult(call.id, call.name, {"value": call.args["value"]})


@pytest.mark.parametrize("case", PROVIDER_CASES, ids=lambda case: case.name)
def test_unicode_and_long_content_round_trip(case: ProviderCase) -> None:
    content = "你好, provider 🌍 — " + ("long-content-" * 1024)
    provider = case.build([ProviderResult(text_message(content))])

    result = run(
        provider,
        ConformanceDispatcher(),
        [text_message(content, role="user")],
        KernelConfig(max_steps=1),
        run_id=f"conformance-{case.name}-unicode",
    )

    assert result.output == text_message(content)


@pytest.mark.parametrize("case", PROVIDER_CASES, ids=lambda case: case.name)
def test_multi_turn_tool_round_trip(case: ProviderCase) -> None:
    call = ToolCall("call-1", "lookup", {"value": 7})
    provider = case.build(
        [ProviderResult(tool_message(call)), ProviderResult(text_message("value=7"))]
    )
    dispatcher = ConformanceDispatcher()

    result = run(
        provider,
        dispatcher,
        [text_message("lookup 7", role="user")],
        KernelConfig(max_steps=2, max_tool_calls=1),
        run_id=f"conformance-{case.name}-tool",
    )

    assert result.output == text_message("value=7")
    assert dispatcher.calls == [call]
    assert [event.type for event in result.events].count("provider_called") == 2
    assert [event.type for event in result.events].count("tool_returned") == 1


@pytest.mark.parametrize("case", PROVIDER_CASES, ids=lambda case: case.name)
def test_parallel_tool_calls_preserve_order(case: ProviderCase) -> None:
    provider = case.build(
        [
            ProviderResult(
                tool_message(
                    ToolCall("call-1", "lookup", {"value": 1}),
                    ToolCall("call-2", "lookup", {"value": 2}),
                )
            ),
            ProviderResult(text_message("done")),
        ]
    )
    if not provider.capabilities.supports_parallel_tool_calls:
        pytest.skip("provider capability records no parallel tool-call support")
    dispatcher = ConformanceDispatcher()

    run(
        provider,
        dispatcher,
        [text_message("lookup 1 and 2", role="user")],
        KernelConfig(max_steps=2, max_tool_calls=2),
        run_id=f"conformance-{case.name}-parallel",
    )

    assert [call.id for call in dispatcher.calls] == ["call-1", "call-2"]


@pytest.mark.parametrize("case", PROVIDER_CASES, ids=lambda case: case.name)
def test_retryable_error_uses_kernel_contract(case: ProviderCase) -> None:
    provider = case.build([case.retryable_error()])

    with pytest.raises(RetryableProviderError, match="rate limited"):
        provider.complete([text_message("retry", role="user")])
