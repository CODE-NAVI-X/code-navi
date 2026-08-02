from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from code_navi.online_compiler.deepseek import DeepSeekChatCompletionsAdapter
from kernel.core import ContentBlock, FatalProviderError, Message, ProviderTool


class FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def create(self, **request: Any) -> Any:
        self.requests.append(request)
        return self.response


def _client(response: Any) -> tuple[Any, FakeCompletions]:
    completions = FakeCompletions(response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def test_adapter_translates_text_messages_and_normalizes_usage() -> None:
    response = SimpleNamespace(
        id="response-1",
        model="deepseek-v4-flash",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"explanation":"检查除数。","suggestions":[],"quality":'
                    '{"readability":80,"structure":70,"robustness":40}}'
                ),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=30, total_tokens=50),
        _request_id="request-1",
    )
    client, completions = _client(response)
    adapter = DeepSeekChatCompletionsAdapter(
        "deepseek-v4-flash", client=client, max_output_tokens=700
    )

    result = adapter.complete(
        (
            Message("system", (ContentBlock("text", {"text": "只输出 JSON"}),)),
            Message("user", (ContentBlock("text", {"text": '{"source":"1 / 0"}'}),)),
        )
    )

    assert completions.requests == [
        {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": "只输出 JSON"},
                {"role": "user", "content": '{"source":"1 / 0"}'},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
            "max_tokens": 700,
        }
    ]
    assert result.message.content[0].data["text"].startswith('{"explanation"')
    assert result.usage == {
        "input_tokens": 20,
        "output_tokens": 30,
        "total_tokens": 50,
    }
    assert result.finish_reason == "stop"
    assert result.metadata["provider"] == "deepseek"


def test_adapter_rejects_tools_because_evaluator_is_text_only() -> None:
    client, _ = _client(None)
    adapter = DeepSeekChatCompletionsAdapter("deepseek-v4-flash", client=client)
    tool = ProviderTool("lookup", "Look up a value.", {"type": "object", "properties": {}})

    with pytest.raises(FatalProviderError, match="does not expose tools"):
        adapter.complete((), (tool,))


def test_adapter_rejects_empty_completion() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="stop")]
    )
    client, _ = _client(response)
    adapter = DeepSeekChatCompletionsAdapter("deepseek-v4-flash", client=client)

    with pytest.raises(FatalProviderError, match="empty message content"):
        adapter.complete((Message("user", (ContentBlock("text", {"text": "{}"}),)),))
