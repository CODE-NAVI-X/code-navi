from kernel.core import (
    Message,
    MockProvider,
    ProviderResult,
    RunStatus,
    TailWithSummary,
    ToolResult,
    run,
)


class UnitCounter:
    def count(self, messages) -> int:
        return len(messages)


class Summarizer:
    def summarize(self, messages, budget_tokens: int) -> str:
        return "summary"


class Dispatcher:
    def dispatch(self, call) -> ToolResult:
        return ToolResult(call.id, call.name, None)


def test_pinned_budget_failure_uses_fatal_context_reason() -> None:
    provider = MockProvider([ProviderResult(Message("assistant"))])
    policy = TailWithSummary(UnitCounter(), Summarizer(), summary_budget_tokens=1)

    result = run(
        provider,
        Dispatcher(),
        [Message("system", pinned=True), Message("user", pinned=True)],
        context_policy=policy,
        context_budget_tokens=1,
    )

    assert result.status == RunStatus.FATAL_ERROR
    assert result.reason == "context_budget_exceeded"
    assert provider.calls == []
    assert result.events[-2].type == "error"
    assert result.events[-2].payload["source"] == "kernel"
    assert result.events[-1].payload == {
        "status": "fatal_error",
        "reason": "context_budget_exceeded",
    }
