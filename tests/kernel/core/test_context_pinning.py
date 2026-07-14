import pytest

from kernel.core import (
    ContentBlock,
    ContextBudgetExceeded,
    Event,
    FullHistory,
    Message,
    TailWithSummary,
)


class UnitCounter:
    def count(self, messages) -> int:
        return len(messages)


class RecordingSummarizer:
    def __init__(self) -> None:
        self.calls = []

    def summarize(self, messages, budget_tokens: int) -> str:
        self.calls.append((tuple(messages), budget_tokens))
        return "rolling summary"


class SummaryCostsTwoCounter:
    def count(self, messages) -> int:
        return sum(
            2 if item.metadata.get("context_kind") == "rolling_summary" else 1
            for item in messages
        )


def message(text: str, *, pinned: bool = False) -> Message:
    return Message(
        "user",
        (ContentBlock("text", {"text": text}),),
        pinned=pinned,
    )


def history(*messages: Message) -> list[Event]:
    return [
        Event(
            f"e{seq}",
            "run-1",
            seq,
            f"2026-07-14T00:00:{seq:02d}Z",
            "message_added",
            {"message": item.to_json()},
        )
        for seq, item in enumerate(messages)
    ]


def test_full_history_returns_structured_view_without_compression() -> None:
    events = history(message("one"), message("two"))

    view = FullHistory().view(events, budget_tokens=1)

    assert view.messages == (message("one"), message("two"))
    assert view.compression is None


@pytest.mark.parametrize("budget", range(3, 6))
def test_pinned_message_is_verbatim_at_every_viable_budget(budget: int) -> None:
    pinned = message("final output requires xyzzy", pinned=True)
    events = history(
        message("old-1"),
        pinned,
        message("old-2"),
        message("old-3"),
        message("recent"),
        message("latest"),
    )
    policy = TailWithSummary(UnitCounter(), RecordingSummarizer(), summary_budget_tokens=1)
    original_events = tuple(events)

    view = policy.view(events, budget)

    assert tuple(events) == original_events
    assert sum(item.to_json() == pinned.to_json() for item in view.messages) == 1
    assert view.messages[-1] == message("latest")
    assert UnitCounter().count(view.messages) <= budget
    assert view.compression is not None


def test_pinned_content_over_budget_is_never_silently_dropped() -> None:
    events = history(message("pin-1", pinned=True), message("pin-2", pinned=True))
    policy = TailWithSummary(UnitCounter(), RecordingSummarizer(), summary_budget_tokens=1)

    with pytest.raises(ContextBudgetExceeded, match="pinned"):
        policy.view(events, budget_tokens=1)


def test_equivalent_recorded_compression_is_reused_without_a_new_plan() -> None:
    summarizer = RecordingSummarizer()
    policy = TailWithSummary(UnitCounter(), summarizer, summary_budget_tokens=1)
    events = history(
        message("pin", pinned=True),
        message("old-1"),
        message("old-2"),
        message("recent"),
    )
    first = policy.view(events, budget_tokens=3)
    assert first.compression is not None
    compression_event = Event(
        "compressed-1",
        "run-1",
        4,
        "2026-07-14T00:00:04Z",
        "context_compressed",
        first.compression.to_payload(),
    )

    second = policy.view([*events, compression_event], budget_tokens=3)

    assert second.messages == first.messages
    assert second.compression is None
    assert len(summarizer.calls) == 1


def test_recorded_compression_is_rechecked_against_current_budget() -> None:
    events = history(
        message("pin", pinned=True),
        message("old-1"),
        message("old-2"),
        message("old-3"),
        message("recent"),
    )
    first_policy = TailWithSummary(
        SummaryCostsTwoCounter(), RecordingSummarizer(), summary_budget_tokens=2
    )
    first = first_policy.view(events, budget_tokens=4)
    assert first.compression is not None
    recorded = Event(
        "compressed-1",
        "run-1",
        5,
        "2026-07-14T00:00:05Z",
        "context_compressed",
        first.compression.to_payload(),
    )
    resumed_policy = TailWithSummary(
        SummaryCostsTwoCounter(), RecordingSummarizer(), summary_budget_tokens=1
    )

    with pytest.raises(ContextBudgetExceeded, match="recorded summary"):
        resumed_policy.view([*events, recorded], budget_tokens=3)
