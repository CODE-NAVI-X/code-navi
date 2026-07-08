from kernel.core import (
    ContentBlock,
    Event,
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


def test_resume_with_inflight_tool_call_fails_fatally() -> None:
    call = ToolCall("tc1", "write", {"path": "x"})
    prior = [
        Event("e0", "r1", 0, "2026-07-08T00:00:00Z", "run_started", {}),
        Event("e1", "r1", 1, "2026-07-08T00:00:01Z", "message_added", {"message": Message("user").to_json()}),
        Event(
            "e2",
            "r1",
            2,
            "2026-07-08T00:00:02Z",
            "message_added",
            {
                "message": Message(
                    "assistant",
                    (ContentBlock("tool_use", {"tool_call": call.to_json()}),),
                ).to_json()
            },
        ),
        Event("e3", "r1", 3, "2026-07-08T00:00:03Z", "tool_called", {"tool_call": call.to_json()}),
    ]
    provider = MockProvider([ProviderResult(Message("assistant"))])
    dispatcher = Dispatcher()

    result = run(
        provider,
        dispatcher,
        [],
        KernelConfig(max_steps=0, max_tool_calls=0),
        prior_events=prior,
        interrupt_check=lambda: True,
    )

    assert result.status == RunStatus.FATAL_ERROR
    assert result.reason == "unsafe_resume_inflight_tool"
    assert provider.calls == []
    assert dispatcher.calls == []
    assert result.events[: len(prior)] == tuple(prior)
    assert result.events[len(prior)].seq == 4
    assert result.events[-2].payload == {
        "source": "kernel",
        "classification": "fatal",
        "message": "unsafe resume: in-flight tool call",
        "attempt": None,
    }
    assert result.events[-1].payload == {
        "status": "fatal_error",
        "reason": "unsafe_resume_inflight_tool",
    }
    assert result.state.run_id == "r1"


def test_resume_after_returned_tool_does_not_repeat_tools() -> None:
    call = ToolCall("tc1", "write", {"path": "x"})
    tool_result = ToolResult(call.id, call.name, {"ok": True})
    prior = [
        Event("e0", "r1", 0, "2026-07-08T00:00:00Z", "run_started", {}),
        Event("e1", "r1", 1, "2026-07-08T00:00:01Z", "message_added", {"message": Message("user").to_json()}),
        Event(
            "e2",
            "r1",
            2,
            "2026-07-08T00:00:02Z",
            "message_added",
            {"message": Message("assistant", (ContentBlock("tool_use", {"tool_call": call.to_json()}),)).to_json()},
        ),
        Event("e3", "r1", 3, "2026-07-08T00:00:03Z", "tool_called", {"tool_call": call.to_json()}),
        Event("e4", "r1", 4, "2026-07-08T00:00:04Z", "tool_returned", {"tool_result": tool_result.to_json()}),
        Event("e5", "r1", 5, "2026-07-08T00:00:05Z", "message_added", {"message": Message("tool").to_json()}),
    ]
    dispatcher = Dispatcher()

    result = run(
        MockProvider([ProviderResult(Message("assistant"))]),
        dispatcher,
        [],
        KernelConfig(max_steps=3, max_tool_calls=5),
        prior_events=prior,
    )

    assert result.status == RunStatus.COMPLETED
    assert result.reason == "completed"
    assert dispatcher.calls == []
    assert result.events[: len(prior)] == tuple(prior)
    assert result.events[len(prior)].seq == 6


def test_interrupted_terminal_prior_events_are_not_resumed() -> None:
    prior = [
        Event("e0", "r2", 0, "2026-07-08T00:00:00Z", "run_started", {}),
        Event("e1", "r2", 1, "2026-07-08T00:00:01Z", "interrupted", {}),
        Event(
            "e2",
            "r2",
            2,
            "2026-07-08T00:00:02Z",
            "run_finished",
            {"status": "interrupted", "reason": "interrupted"},
        ),
    ]
    provider = MockProvider([ProviderResult(Message("assistant"))])
    dispatcher = Dispatcher()

    result = run(provider, dispatcher, [], prior_events=prior)

    assert result.status == RunStatus.INTERRUPTED
    assert result.reason == "interrupted"
    assert result.events == tuple(prior)
    assert provider.calls == []
    assert dispatcher.calls == []


def test_interrupted_prefix_without_run_finished_is_kernel_error() -> None:
    prior = [
        Event("e0", "r3", 0, "2026-07-08T00:00:00Z", "run_started", {}),
        Event("e1", "r3", 1, "2026-07-08T00:00:01Z", "interrupted", {}),
    ]
    provider = MockProvider([ProviderResult(Message("assistant"))])
    dispatcher = Dispatcher()

    result = run(provider, dispatcher, [], prior_events=prior)

    assert result.status == RunStatus.FATAL_ERROR
    assert result.reason == "kernel_error"
    assert provider.calls == []
    assert dispatcher.calls == []
    assert result.events[: len(prior)] == tuple(prior)
    assert result.events[-2].type == "error"
    assert result.events[-2].payload["source"] == "kernel"
    assert result.events[-1].payload == {"status": "fatal_error", "reason": "kernel_error"}
