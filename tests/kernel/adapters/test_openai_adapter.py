import json
from pathlib import Path
from types import SimpleNamespace

import pytest

httpx = pytest.importorskip("httpx")
openai = pytest.importorskip("openai")

from kernel.adapters.jsonl_session import load_session, save_session  # noqa: E402
from kernel.adapters.openai import OpenAIResponsesAdapter  # noqa: E402
from kernel.core import (  # noqa: E402
    ContentBlock,
    FatalProviderError,
    KernelConfig,
    Message,
    PermissionGrant,
    ProviderTool,
    RetryableProviderError,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
    run,
)
from kernel.providers import ReplayProvider  # noqa: E402


class FakeResponses:
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
        self.responses = FakeResponses(script)
        self.options: list[dict] = []

    def with_options(self, **options):
        self.options.append(options)
        return self


def native_text(text: str, *, usage=(3, 2, 5)):
    return SimpleNamespace(
        id="resp-text",
        model="recorded-model",
        status="completed",
        _request_id="req-text",
        usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1], total_tokens=usage[2]),
        output=(
            SimpleNamespace(
                type="message",
                content=(SimpleNamespace(type="output_text", text=text),),
            ),
        ),
    )


def native_tool_calls(*calls: tuple[str, str, str]):
    return SimpleNamespace(
        id="resp-tools",
        model="recorded-model",
        status="completed",
        _request_id="req-tools",
        usage=SimpleNamespace(input_tokens=4, output_tokens=3, total_tokens=7),
        output=tuple(
            SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=args)
            for call_id, name, args in calls
        ),
    )


def status_error(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status, request=request)
    return openai.APIStatusError(f"status {status}", response=response, body={"error": "recorded"})


def text_message(text: str, *, role: str = "user") -> Message:
    return Message(role, (ContentBlock("text", {"text": text}),))


def test_request_translation_is_stateless_non_strict_and_sdk_retry_free() -> None:
    client = FakeClient([native_text("done")])
    adapter = OpenAIResponsesAdapter("explicit-model", client=client, max_output_tokens=64)
    tool = ProviderTool(
        "lookup",
        "Look up a value.",
        {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )

    result = adapter.complete([text_message("你好 🌍")], [tool])

    assert client.options == [{"max_retries": 0}]
    assert client.responses.requests == [
        {
            "model": "explicit-model",
            "input": [{"role": "user", "content": "你好 🌍"}],
            "tools": [
                {
                    "type": "function",
                    "name": "lookup",
                    "description": "Look up a value.",
                    "parameters": dict(tool.args_schema),
                    "strict": False,
                }
            ],
            "store": False,
            "max_output_tokens": 64,
        }
    ]
    assert result.message == text_message("done", role="assistant")
    assert result.usage == {
        "input_tokens": 3,
        "output_tokens": 2,
        "total_tokens": 5,
    }
    assert result.metadata["request_id"] == "req-text"


def test_adapter_passes_timeout_to_sdk_transport() -> None:
    client = FakeClient([native_text("done")])

    adapter = OpenAIResponsesAdapter("explicit-model", client=client, timeout=2.5)
    adapter.complete([text_message("bounded")])

    assert client.options == [{"max_retries": 0, "timeout": 2.5}]


def test_official_sdk_serializes_recorded_request_and_parses_response() -> None:
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "x-request-id": "req-sdk"},
            json={
                "id": "resp-sdk",
                "created_at": 1.0,
                "error": None,
                "incomplete_details": None,
                "instructions": None,
                "metadata": {},
                "model": "recorded-model",
                "object": "response",
                "output": [
                    {
                        "id": "msg-sdk",
                        "content": [
                            {
                                "annotations": [],
                                "logprobs": [],
                                "text": "sdk-done",
                                "type": "output_text",
                            }
                        ],
                        "role": "assistant",
                        "status": "completed",
                        "type": "message",
                    }
                ],
                "parallel_tool_calls": True,
                "status": "completed",
                "temperature": None,
                "tool_choice": "auto",
                "tools": [],
                "top_p": None,
                "usage": {
                    "input_tokens": 3,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 2,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 5,
                },
            },
        )

    sdk_client = openai.OpenAI(
        api_key="recorded-test-key",
        max_retries=7,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter = OpenAIResponsesAdapter("recorded-model", client=sdk_client, max_output_tokens=64)
    tool = ProviderTool(
        "lookup",
        "Look up a value.",
        {"type": "object", "additionalProperties": False},
    )

    result = adapter.complete([text_message("use the tool")], [tool])

    assert result.message == text_message("sdk-done", role="assistant")
    assert result.metadata["request_id"] == "req-sdk"
    assert captured == [
        {
            "input": [{"role": "user", "content": "use the tool"}],
            "max_output_tokens": 64,
            "model": "recorded-model",
            "store": False,
            "tools": [
                {
                    "description": "Look up a value.",
                    "name": "lookup",
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                    },
                    "strict": False,
                    "type": "function",
                }
            ],
        }
    ]


def test_multiple_function_calls_preserve_native_order() -> None:
    adapter = OpenAIResponsesAdapter(
        "explicit-model",
        client=FakeClient(
            [
                native_tool_calls(
                    ("call-2", "lookup", '{"value":2}'),
                    ("call-1", "lookup", '{"value":1}'),
                )
            ]
        ),
    )

    result = adapter.complete([text_message("two calls")])

    calls = [block.data["tool_call"] for block in result.message.content]
    assert [call["id"] for call in calls] == ["call-2", "call-1"]
    assert result.finish_reason == "tool_use"


@pytest.mark.parametrize("block_type", ["image_ref", "artifact_ref"])
def test_unsupported_reference_blocks_are_fatal(block_type: str) -> None:
    adapter = OpenAIResponsesAdapter("explicit-model", client=FakeClient([]))
    message = Message("user", (ContentBlock(block_type, {"uri": "file:///x"}),))

    with pytest.raises(FatalProviderError, match=block_type):
        adapter.complete([message])


@pytest.mark.parametrize("status", [408, 409, 429, 500, 503])
def test_retryable_status_mapping(status: int) -> None:
    adapter = OpenAIResponsesAdapter("explicit-model", client=FakeClient([status_error(status)]))

    with pytest.raises(RetryableProviderError, match=f"status {status}"):
        adapter.complete([text_message("retry")])


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_fatal_status_mapping(status: int) -> None:
    adapter = OpenAIResponsesAdapter("explicit-model", client=FakeClient([status_error(status)]))

    with pytest.raises(FatalProviderError, match=f"status {status}"):
        adapter.complete([text_message("fatal")])


@pytest.mark.parametrize(
    "error",
    [
        openai.APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com/v1/responses")
        ),
        openai.APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")),
    ],
)
def test_connection_and_timeout_are_retryable(error: openai.APIError) -> None:
    adapter = OpenAIResponsesAdapter("explicit-model", client=FakeClient([error]))

    with pytest.raises(RetryableProviderError):
        adapter.complete([text_message("retry")])


def test_official_sdk_retries_are_disabled_by_adapter() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            500,
            headers={"content-type": "application/json"},
            json={
                "error": {
                    "message": "recorded server error",
                    "type": "server_error",
                    "param": None,
                    "code": "server_error",
                }
            },
        )

    sdk_client = openai.OpenAI(
        api_key="recorded-test-key",
        max_retries=7,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter = OpenAIResponsesAdapter("recorded-model", client=sdk_client)

    with pytest.raises(RetryableProviderError, match="recorded server error"):
        adapter.complete([text_message("retry once")])

    assert requests == 1


def test_response_validation_error_is_fatal() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(200, request=request)
    error = openai.APIResponseValidationError(
        response=response,
        body={"invalid": "response"},
        message="invalid recorded response",
    )
    adapter = OpenAIResponsesAdapter("recorded-model", client=FakeClient([error]))

    with pytest.raises(FatalProviderError, match="invalid recorded response"):
        adapter.complete([text_message("fatal")])


def test_invalid_function_arguments_are_fatal() -> None:
    adapter = OpenAIResponsesAdapter(
        "explicit-model",
        client=FakeClient([native_tool_calls(("call-1", "lookup", "not-json"))]),
    )

    with pytest.raises(FatalProviderError, match="not valid JSON"):
        adapter.complete([text_message("bad call")])


def read_dispatcher(scope: str):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "lookup",
            "Look up a deterministic local value.",
            {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            frozenset({ToolPermission.READ}),
        ),
        lambda args, context: {"value": args["value"]},
    )
    return registry.bind(PermissionGrant(scope), ToolExecutionContext(scope))


def without_timestamps(events):
    return [
        {key: value for key, value in event.to_json().items() if key != "timestamp"}
        for event in events
    ]


def test_recorded_openai_run_has_jsonl_replay_identity(tmp_path: Path) -> None:
    run_id = "openai-recorded-replay"
    initial = [text_message("lookup 7")]
    adapter = OpenAIResponsesAdapter(
        "explicit-model",
        client=FakeClient(
            [
                native_tool_calls(("call-1", "lookup", '{"value":7}')),
                native_text("value=7"),
            ]
        ),
    )
    recorded = run(
        adapter,
        read_dispatcher(run_id),
        initial,
        KernelConfig(max_steps=2, max_tool_calls=1),
        run_id=run_id,
    )
    path = tmp_path / "openai.jsonl"
    save_session(path, recorded.events)

    loaded = load_session(path)
    replay = ReplayProvider(loaded)
    replayed = run(
        replay,
        read_dispatcher(run_id),
        initial,
        KernelConfig(max_steps=2, max_tool_calls=1),
        run_id=run_id,
    )
    replay.assert_consumed()

    assert without_timestamps(replayed.events) == without_timestamps(recorded.events)
