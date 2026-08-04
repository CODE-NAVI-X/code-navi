from types import SimpleNamespace

import pytest

httpx = pytest.importorskip("httpx")
openai = pytest.importorskip("openai")

from kernel.adapters.openai_chat import OpenAIChatCompletionsAdapter  # noqa: E402
from kernel.core import (  # noqa: E402
    ContentBlock,
    FatalProviderError,
    Message,
    ProviderTool,
    RetryableProviderError,
    ToolCall,
)


class FakeChatCompletions:
    def __init__(self, script) -> None:
        self.script = list(script)
        self.requests: list[dict] = []

    def create(self, **request):
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, script) -> None:
        self.chat = SimpleNamespace(completions=FakeChatCompletions(script))
        self.options: list[dict] = []

    def with_options(self, **options):
        self.options.append(options)
        return self


def native_text(text: str, *, usage=(3, 2, 5)):
    return SimpleNamespace(
        id="chat-text",
        model="recorded-model",
        _request_id="req-chat",
        usage=SimpleNamespace(
            prompt_tokens=usage[0],
            completion_tokens=usage[1],
            total_tokens=usage[2],
        ),
        choices=(
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=text, tool_calls=None),
            ),
        ),
    )


def native_tool_call(call_id: str, name: str, args: str):
    return SimpleNamespace(
        id="chat-tools",
        model="recorded-model",
        choices=(
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    tool_calls=(
                        SimpleNamespace(
                            id=call_id,
                            function=SimpleNamespace(name=name, arguments=args),
                        ),
                    ),
                ),
            ),
        ),
    )


def status_error(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(status, request=request)
    return openai.APIStatusError(f"status {status}", response=response, body={"error": "recorded"})


def text_message(text: str, *, role: str = "user") -> Message:
    return Message(role, (ContentBlock("text", {"text": text}),))


def test_chat_request_translation_supports_tools_and_usage() -> None:
    client = FakeClient([native_text("done")])
    adapter = OpenAIChatCompletionsAdapter(
        "deepseek-v4-pro",
        client=client,
        provider_name="deepseek",
        max_tokens=64,
    )
    tool = ProviderTool(
        "lookup",
        "Look up a value.",
        {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )

    result = adapter.complete([text_message("你好")], [tool])

    assert client.options == [{"max_retries": 0}]
    assert client.chat.completions.requests == [
        {
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "你好"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Look up a value.",
                        "parameters": dict(tool.args_schema),
                    },
                }
            ],
            "max_tokens": 64,
        }
    ]
    assert result.message == text_message("done", role="assistant")
    assert result.usage == {
        "input_tokens": 3,
        "output_tokens": 2,
        "total_tokens": 5,
    }
    assert result.metadata["provider"] == "deepseek"
    assert result.metadata["request_id"] == "req-chat"


def test_chat_tool_calls_parse_to_runtime_blocks() -> None:
    adapter = OpenAIChatCompletionsAdapter(
        "deepseek-v4-pro",
        client=FakeClient([native_tool_call("call-1", "lookup", '{"value":7}')]),
    )

    result = adapter.complete([text_message("use tool")])

    assert result.finish_reason == "tool_calls"
    assert [block.data["tool_call"] for block in result.message.content] == [
        ToolCall("call-1", "lookup", {"value": 7}).to_json()
    ]


@pytest.mark.parametrize("status", [408, 409, 429, 500])
def test_chat_retryable_status_mapping(status: int) -> None:
    adapter = OpenAIChatCompletionsAdapter(
        "deepseek-v4-pro",
        client=FakeClient([status_error(status)]),
    )

    with pytest.raises(RetryableProviderError, match=f"status {status}"):
        adapter.complete([text_message("retry")])


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_chat_fatal_status_mapping(status: int) -> None:
    adapter = OpenAIChatCompletionsAdapter(
        "deepseek-v4-pro",
        client=FakeClient([status_error(status)]),
    )

    with pytest.raises(FatalProviderError, match=f"status {status}"):
        adapter.complete([text_message("fatal")])


def test_chat_invalid_tool_arguments_are_fatal() -> None:
    adapter = OpenAIChatCompletionsAdapter(
        "deepseek-v4-pro",
        client=FakeClient([native_tool_call("call-1", "lookup", "not-json")]),
    )

    with pytest.raises(FatalProviderError, match="not valid JSON"):
        adapter.complete([text_message("bad call")])


def test_chat_thinking_disabled_sets_extra_body() -> None:
    client = FakeClient([native_text("done")])
    adapter = OpenAIChatCompletionsAdapter(
        "deepseek-v4-flash",
        client=client,
        thinking="disabled",
    )

    adapter.complete([text_message("gen")])

    assert client.chat.completions.requests[0]["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_chat_thinking_unset_leaves_request_unchanged() -> None:
    client = FakeClient([native_text("done")])
    adapter = OpenAIChatCompletionsAdapter("deepseek-v4-flash", client=client)

    adapter.complete([text_message("gen")])

    assert "extra_body" not in client.chat.completions.requests[0]


def test_chat_rejects_invalid_thinking_value() -> None:
    with pytest.raises(ValueError, match="thinking"):
        OpenAIChatCompletionsAdapter(
            "deepseek-v4-flash",
            client=FakeClient([]),
            thinking="sometimes",
        )
