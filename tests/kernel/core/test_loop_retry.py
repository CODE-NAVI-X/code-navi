from kernel.core import (
    FatalProviderError,
    KernelConfig,
    Message,
    ProviderResult,
    RetryableProviderError,
    RunStatus,
    ToolCall,
    ToolResult,
    run,
)
from kernel.providers import MockProvider


class Dispatcher:
    def provider_tools(self):
        return ()

    def dispatch(self, call: ToolCall) -> ToolResult:
        return ToolResult(call.id, call.name, {"ok": True})


def test_retryable_provider_error_backs_off_and_succeeds() -> None:
    slept = []
    result = run(
        MockProvider([RetryableProviderError("rate"), ProviderResult(Message("assistant"))]),
        Dispatcher(),
        [Message("user")],
        KernelConfig(retry_backoff_seconds=0.25),
        sleeper=slept.append,
    )

    assert result.status == RunStatus.COMPLETED
    assert result.reason == "completed"
    assert slept == [0.25]
    error = [event for event in result.events if event.type == "error"][0]
    assert error.payload == {
        "source": "provider",
        "classification": "retryable",
        "message": "rate",
        "attempt": 1,
    }


def test_fatal_provider_error_exits_without_retry_or_sleep() -> None:
    slept = []
    result = run(
        MockProvider([FatalProviderError("auth")]),
        Dispatcher(),
        [Message("user")],
        KernelConfig(retry_max_attempts=3),
        sleeper=slept.append,
    )

    assert result.status == RunStatus.FATAL_ERROR
    assert result.reason == "fatal_provider_error"
    assert slept == []
    assert len([event for event in result.events if event.type == "error"]) == 1


def test_unknown_provider_error_is_fatal_without_retry_or_sleep() -> None:
    slept = []
    result = run(
        MockProvider([RuntimeError("adapter bug")]),
        Dispatcher(),
        [Message("user")],
        KernelConfig(retry_max_attempts=3),
        sleeper=slept.append,
    )

    assert result.status == RunStatus.FATAL_ERROR
    assert result.reason == "fatal_provider_error"
    assert slept == []
    error = [event for event in result.events if event.type == "error"][0]
    assert error.payload["classification"] == "fatal"


def test_retry_exhaustion_keeps_retryable_error_and_finishes_fatal() -> None:
    slept = []
    result = run(
        MockProvider([RetryableProviderError("busy"), RetryableProviderError("busy")]),
        Dispatcher(),
        [Message("user")],
        KernelConfig(retry_max_attempts=1, retry_backoff_seconds=0.25),
        sleeper=slept.append,
    )

    errors = [event for event in result.events if event.type == "error"]
    assert result.status == RunStatus.FATAL_ERROR
    assert result.reason == "retry_exhausted"
    assert slept == [0.25]
    assert [error.payload["classification"] for error in errors] == ["retryable", "retryable"]
    assert [error.payload["attempt"] for error in errors] == [1, 2]
    assert result.events[-1].payload == {"status": "fatal_error", "reason": "retry_exhausted"}
