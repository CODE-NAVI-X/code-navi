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


class Dispatcher:
    def __init__(self) -> None:
        self.calls = []

    def dispatch(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult(call.id, call.name, {"ok": True})


def tool_message() -> Message:
    call = ToolCall("tc1", "lookup", {"q": "x"})
    return Message("assistant", (ContentBlock("tool_use", {"tool_call": call.to_json()}),))


def test_interrupt_at_iteration_top_exits_before_budget_or_provider() -> None:
    provider = MockProvider([ProviderResult(Message("assistant"))])
    result = run(
        provider,
        Dispatcher(),
        [Message("user")],
        KernelConfig(max_steps=0),
        interrupt_check=lambda: True,
    )

    assert result.status == RunStatus.INTERRUPTED
    assert result.reason == "interrupted"
    assert provider.calls == []
    assert [event.type for event in result.events][-2:] == ["interrupted", "run_finished"]
    assert result.events[-1].payload == {"status": "interrupted", "reason": "interrupted"}


def test_interrupt_before_tool_dispatch_exits_without_tool_called() -> None:
    checks = iter([False, True])
    dispatcher = Dispatcher()
    result = run(
        MockProvider([ProviderResult(tool_message())]),
        dispatcher,
        [Message("user")],
        KernelConfig(max_steps=3, max_tool_calls=0),
        interrupt_check=lambda: next(checks),
    )

    assert result.status == RunStatus.INTERRUPTED
    assert result.reason == "interrupted"
    assert dispatcher.calls == []
    assert not any(event.type == "tool_called" for event in result.events)
