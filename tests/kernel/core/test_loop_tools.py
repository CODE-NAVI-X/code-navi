from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    MockProvider,
    ProviderResult,
    RunStatus,
    ToolCall,
    ToolResult,
    run,
)


def tool_message() -> Message:
    call = ToolCall("tc1", "lookup", {"q": "x"})
    return Message("assistant", (ContentBlock("tool_use", {"tool_call": call.to_json()}),))


class ReturningDispatcher:
    def dispatch(self, call: ToolCall) -> ToolResult:
        return ToolResult(call.id, call.name, {"ok": True})


class RaisingDispatcher:
    def __init__(self) -> None:
        self.calls = []

    def dispatch(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        raise RuntimeError("dispatcher down")


def test_tool_dispatch_event_order_and_tool_result_message() -> None:
    result = run(
        MockProvider([ProviderResult(tool_message()), ProviderResult(Message("assistant"))]),
        ReturningDispatcher(),
        [Message("user")],
        KernelConfig(max_steps=3, max_tool_calls=2),
    )

    event_types = [event.type for event in result.events]
    index = event_types.index("tool_called")
    assert event_types[index : index + 4] == [
        "tool_called",
        "budget_updated",
        "tool_returned",
        "message_added",
    ]
    message = result.events[index + 3].payload["message"]
    assert message["content"][0]["type"] == "tool_result"
    assert result.status == RunStatus.COMPLETED
    assert result.reason == "completed"


def test_dispatcher_raise_is_fatal_tool_error_after_counting_attempt() -> None:
    dispatcher = RaisingDispatcher()
    result = run(
        MockProvider([ProviderResult(tool_message())]),
        dispatcher,
        [Message("user")],
        KernelConfig(max_steps=3, max_tool_calls=2),
    )

    assert result.status == RunStatus.FATAL_ERROR
    assert result.reason == "fatal_tool_error"
    assert len(dispatcher.calls) == 1
    assert [event for event in result.events if event.type == "budget_updated"][-1].payload[
        "used_tool_calls"
    ] == 1
    error = [event for event in result.events if event.type == "error"][0]
    assert error.payload["source"] == "tool"
    assert error.payload["classification"] == "fatal"
    assert error.payload["attempt"] is None
