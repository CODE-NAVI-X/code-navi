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


def tool_message() -> Message:
    call = ToolCall("tc1", "lookup", {"q": "x"})
    return Message("assistant", (ContentBlock("tool_use", {"tool_call": call.to_json()}),))


def test_step_budget_exhaustion_is_clean_and_resume_finishes() -> None:
    first_dispatcher = Dispatcher()
    first = run(
        MockProvider([ProviderResult(tool_message())]),
        first_dispatcher,
        [Message("user")],
        KernelConfig(max_steps=1, max_tool_calls=5),
    )

    assert first.status == RunStatus.BUDGET_EXHAUSTED
    assert first.reason == "budget_exhausted"
    assert first.events[-1].payload["reason"] == "budget_exhausted"
    assert len(first_dispatcher.calls) == 1

    second_dispatcher = Dispatcher()
    second = run(
        MockProvider([ProviderResult(Message("assistant"))]),
        second_dispatcher,
        [],
        KernelConfig(max_steps=2, max_tool_calls=5),
        prior_events=first.events,
    )

    assert second.status == RunStatus.COMPLETED
    assert second.reason == "completed"
    assert second_dispatcher.calls == []
    assert second.state.steps_used == 2


def test_tool_budget_exhaustion_does_not_dispatch() -> None:
    dispatcher = Dispatcher()
    result = run(
        MockProvider([ProviderResult(tool_message())]),
        dispatcher,
        [Message("user")],
        KernelConfig(max_steps=3, max_tool_calls=0),
    )

    assert result.status == RunStatus.BUDGET_EXHAUSTED
    assert result.reason == "tool_budget_exhausted"
    assert result.events[-1].payload["reason"] == "tool_budget_exhausted"
    assert dispatcher.calls == []
    assert not any(event.type == "tool_called" for event in result.events)
