import copy
from pathlib import Path

from kernel.adapters.jsonl_session import load_session, save_session
from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    MockProvider,
    ProviderResult,
    RetryableProviderError,
    TailWithSummary,
    ToolCall,
    ToolResult,
    run,
)
from kernel.providers import ReplayProvider


class UnitCounter:
    def count(self, messages) -> int:
        return len(messages)


class ConstantSummarizer:
    def summarize(self, messages, budget_tokens: int) -> str:
        return "summary"


class Dispatcher:
    def dispatch(self, call: ToolCall) -> ToolResult:
        return ToolResult(call.id, call.name, {"value": call.args["value"]})


def text(value: str, *, role: str = "user") -> Message:
    return Message(role, (ContentBlock("text", {"text": value}),))


def tool_step(call_id: str, value: int) -> ProviderResult:
    call = ToolCall(call_id, "echo", {"value": value})
    return ProviderResult(
        Message(
            "assistant",
            (ContentBlock("tool_use", {"tool_call": call.to_json()}),),
        ),
        {"input_tokens": value, "output_tokens": 1},
        "tool_use",
        {"step": value},
    )


def semantic_events(events) -> list[dict]:
    encoded = copy.deepcopy([event.to_json() for event in events])
    for event in encoded:
        del event["timestamp"]
    return encoded


def test_record_save_load_and_replay_three_steps_identically(tmp_path: Path) -> None:
    initial = tuple(text(f"initial-{index}") for index in range(4))
    config = KernelConfig(
        max_steps=3,
        max_tool_calls=3,
        retry_max_attempts=2,
        retry_backoff_seconds=0,
    )

    def policy() -> TailWithSummary:
        return TailWithSummary(
            UnitCounter(), ConstantSummarizer(), summary_budget_tokens=1
        )

    recorded = run(
        MockProvider(
            [
                RetryableProviderError("temporary"),
                tool_step("tc-1", 1),
                tool_step("tc-2", 2),
                ProviderResult(
                    text("done", role="assistant"),
                    {"input_tokens": 3, "output_tokens": 1},
                    "stop",
                    {"step": 3},
                ),
            ]
        ),
        Dispatcher(),
        initial,
        config,
        context_policy=policy(),
        context_budget_tokens=3,
        sleeper=lambda seconds: None,
    )
    recorded_path = tmp_path / "recorded.jsonl"
    save_session(recorded_path, recorded.events)
    loaded = load_session(recorded_path)

    replay_provider = ReplayProvider(loaded)
    replayed = run(
        replay_provider,
        Dispatcher(),
        initial,
        config,
        run_id=recorded.state.run_id,
        context_policy=policy(),
        context_budget_tokens=3,
        sleeper=lambda seconds: None,
    )
    replay_provider.assert_consumed()
    replayed_path = tmp_path / "replayed.jsonl"
    save_session(replayed_path, replayed.events)

    event_types = [event.type for event in loaded]
    attempts = [
        event.payload["attempt"] for event in loaded if event.type == "provider_called"
    ]
    assert attempts == [1, 2, 1, 1]
    assert event_types.count("provider_called") == 4
    assert event_types.count("provider_returned") == 3
    assert event_types.count("tool_called") == 2
    assert "context_compressed" in event_types
    for index, event_type in enumerate(event_types):
        if event_type == "provider_returned":
            assert event_types[index + 1 : index + 3] == [
                "budget_updated",
                "message_added",
            ]
    first_call = event_types.index("provider_called")
    assert event_types[first_call : first_call + 2] == ["provider_called", "error"]
    assert semantic_events(load_session(replayed_path)) == semantic_events(loaded)
