import json

from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    ProviderResult,
    RunStatus,
    TailWithSummary,
    ToolCall,
    ToolResult,
    run,
)


class UnitCounter:
    def count(self, messages) -> int:
        return len(messages)


class LongSessionProvider:
    def __init__(self, pinned: Message) -> None:
        self.pinned = pinned
        self.agent_steps = 0
        self.summary_calls = 0
        self.calls = []

    def complete(self, messages, tools=None) -> ProviderResult:
        self.calls.append(tuple(messages))
        if messages and messages[0].metadata.get("context_operation") == "summarize":
            self.summary_calls += 1
            return ProviderResult(text_message(f"summary-{self.summary_calls}"))
        self.agent_steps += 1
        if self.agent_steps < 40:
            call = ToolCall(f"tc-{self.agent_steps}", "filler", {"n": self.agent_steps})
            return ProviderResult(
                Message(
                    "assistant",
                    (ContentBlock("tool_use", {"tool_call": call.to_json()}),),
                )
            )
        retained = any(item.to_json() == self.pinned.to_json() for item in messages)
        value = {"xyzzy": "preserved"} if retained else {"lost": True}
        return ProviderResult(text_message(json.dumps(value)))


class ProviderBackedSummarizer:
    def __init__(self, provider: LongSessionProvider) -> None:
        self.provider = provider

    def summarize(self, messages, budget_tokens: int) -> str:
        request = Message(
            "user",
            (ContentBlock("text", {"text": f"summarize {len(messages)} messages"}),),
            {"context_operation": "summarize", "budget_tokens": budget_tokens},
        )
        result = self.provider.complete((request,))
        return result.message.content[0].data["text"]


class Dispatcher:
    def provider_tools(self):
        return ()

    def dispatch(self, call: ToolCall) -> ToolResult:
        return ToolResult(call.id, call.name, {"ok": True, "n": call.args["n"]})


def text_message(text: str) -> Message:
    return Message("assistant", (ContentBlock("text", {"text": text}),))


def test_early_pinned_constraint_survives_compression_at_step_40() -> None:
    pinned = Message(
        "user",
        (ContentBlock("text", {"text": "Return valid JSON with field xyzzy."}),),
        pinned=True,
    )
    provider = LongSessionProvider(pinned)
    policy = TailWithSummary(
        UnitCounter(), ProviderBackedSummarizer(provider), summary_budget_tokens=1
    )

    result = run(
        provider,
        Dispatcher(),
        [Message("system", pinned=True), pinned],
        KernelConfig(max_steps=45, max_tool_calls=45),
        context_policy=policy,
        context_budget_tokens=6,
    )

    assert result.status == RunStatus.COMPLETED
    assert json.loads(result.output.content[0].data["text"]) == {"xyzzy": "preserved"}
    assert provider.agent_steps == 40
    assert provider.summary_calls > 0
    assert any(event.type == "context_compressed" for event in result.events)
    assert sum(event.type == "message_added" for event in result.events) == 81
