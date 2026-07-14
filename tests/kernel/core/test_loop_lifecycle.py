from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    ProviderResult,
    RunStatus,
    ToolCall,
    ToolResult,
    run,
)
from kernel.providers import MockProvider


class Dispatcher:
    def __init__(self) -> None:
        self.calls = []

    def provider_tools(self):
        return ()

    def dispatch(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult(call.id, call.name, {"ok": True})


def tool_use(call_id: str, name: str = "lookup") -> Message:
    call = ToolCall(call_id, name, {"q": call_id})
    return Message("assistant", (ContentBlock("tool_use", {"tool_call": call.to_json()}),))


def text_message(text: str = "done") -> Message:
    return Message("assistant", (ContentBlock("text", {"text": text}),))


def test_three_step_mock_task_completes() -> None:
    dispatcher = Dispatcher()
    result = run(
        MockProvider(
            [
                ProviderResult(tool_use("tc1")),
                ProviderResult(tool_use("tc2")),
                ProviderResult(text_message()),
            ]
        ),
        dispatcher,
        [Message("user", (ContentBlock("text", {"text": "go"}),))],
        KernelConfig(max_steps=5, max_tool_calls=5),
    )

    assert result.status == RunStatus.COMPLETED
    assert result.reason == "completed"
    assert [call.id for call in dispatcher.calls] == ["tc1", "tc2"]
    event_types = [event.type for event in result.events]
    assert event_types.count("tool_called") == 2
    assert event_types.count("tool_returned") == 2
    assert event_types[-1] == "run_finished"
    assert result.state.steps_used == 3
    assert result.state.tool_calls_used == 2
