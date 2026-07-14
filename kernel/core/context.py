"""S5 provider-visible context views over append-only Event history."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .types import ContentBlock, Event, Message


class ContextBudgetExceeded(RuntimeError):
    """The policy cannot construct a valid view inside the supplied budget."""


class TokenCounter(Protocol):
    """Host- or adapter-supplied exact token counting boundary."""

    def count(self, messages: Sequence[Message]) -> int:
        ...


class Summarizer(Protocol):
    """Host-supplied, normally provider-backed summary boundary."""

    def summarize(
        self, messages: Sequence[Message], budget_tokens: int
    ) -> str:
        ...


@dataclass(frozen=True, slots=True)
class ContextCompression:
    start_seq: int
    end_seq: int
    source_event_ids: tuple[str, ...]
    summary: str
    previous_event_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "start_seq": self.start_seq,
            "end_seq": self.end_seq,
            "source_event_ids": list(self.source_event_ids),
            "summary": self.summary,
            "previous_event_id": self.previous_event_id,
        }


@dataclass(frozen=True, slots=True)
class ContextView:
    messages: tuple[Message, ...]
    compression: ContextCompression | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))


class ContextPolicy(Protocol):
    def view(
        self, events: Sequence[Event], budget_tokens: int
    ) -> ContextView:
        ...


@dataclass(frozen=True, slots=True)
class _MessageEntry:
    event_id: str
    seq: int
    message: Message


def _message_entries(events: Sequence[Event]) -> tuple[_MessageEntry, ...]:
    return tuple(
        _MessageEntry(event.event_id, event.seq, Message.from_json(event.payload["message"]))
        for event in sorted(events, key=lambda item: item.seq)
        if event.type == "message_added"
    )


def _summary_message(summary: str) -> Message:
    return Message(
        "system",
        (ContentBlock("text", {"text": summary}),),
        {"context_kind": "rolling_summary"},
    )


class FullHistory:
    """Default no-op view preserving every message verbatim."""

    def view(
        self, events: Sequence[Event], budget_tokens: int
    ) -> ContextView:
        del budget_tokens
        return ContextView(tuple(entry.message for entry in _message_entries(events)))


class TailWithSummary:
    """Pinned messages, a rolling middle summary, and a recent verbatim tail."""

    def __init__(
        self,
        token_counter: TokenCounter,
        summarizer: Summarizer,
        *,
        summary_budget_tokens: int,
    ) -> None:
        if summary_budget_tokens < 1:
            raise ValueError("summary_budget_tokens must be positive")
        self._token_counter = token_counter
        self._summarizer = summarizer
        self._summary_budget_tokens = summary_budget_tokens

    def view(
        self, events: Sequence[Event], budget_tokens: int
    ) -> ContextView:
        if budget_tokens < 1:
            raise ContextBudgetExceeded("context budget must be positive")
        entries = _message_entries(events)
        all_messages = tuple(entry.message for entry in entries)
        pinned = tuple(entry.message for entry in entries if entry.message.pinned)
        if self._token_counter.count(pinned) > budget_tokens:
            raise ContextBudgetExceeded("pinned content exceeds context budget")
        if self._token_counter.count(all_messages) <= budget_tokens:
            return ContextView(all_messages)

        chosen: tuple[int, tuple[_MessageEntry, ...], tuple[Message, ...]] | None = None
        for cutoff in range(1, len(entries)):
            sources = tuple(
                entry for entry in entries[:cutoff] if not entry.message.pinned
            )
            if not sources:
                continue
            retained = tuple(
                entry.message
                for index, entry in enumerate(entries)
                if entry.message.pinned or index >= cutoff
            )
            if (
                self._token_counter.count(retained) + self._summary_budget_tokens
                <= budget_tokens
            ):
                chosen = cutoff, sources, retained
                break
        if chosen is None:
            raise ContextBudgetExceeded(
                "pinned content, summary, and recent tail exceed context budget"
            )

        cutoff, sources, _ = chosen
        source_ids = tuple(entry.event_id for entry in sources)
        exact = self._exact_compression(events, source_ids)
        if exact is not None:
            summary, _ = exact
            summary_message = _summary_message(summary)
            if (
                self._token_counter.count((summary_message,))
                > self._summary_budget_tokens
            ):
                raise ContextBudgetExceeded(
                    "recorded summary exceeds its current token budget"
                )
            messages = self._assemble(entries, cutoff, source_ids, summary)
            if self._token_counter.count(messages) > budget_tokens:
                raise ContextBudgetExceeded(
                    "recorded context view exceeds context budget"
                )
            return ContextView(messages)

        previous = self._previous_compression(events, source_ids)
        if previous is None:
            summary_inputs = tuple(entry.message for entry in sources)
            previous_event_id = None
        else:
            previous_event, previous_ids, previous_summary = previous
            delta_ids = set(source_ids[len(previous_ids) :])
            summary_inputs = (_summary_message(previous_summary),) + tuple(
                entry.message for entry in sources if entry.event_id in delta_ids
            )
            previous_event_id = previous_event.event_id
        summary = self._summarizer.summarize(
            summary_inputs, self._summary_budget_tokens
        )
        if not isinstance(summary, str):
            raise TypeError("summarizer must return str")
        summary_message = _summary_message(summary)
        if self._token_counter.count((summary_message,)) > self._summary_budget_tokens:
            raise ContextBudgetExceeded("summary exceeds its token budget")
        messages = self._assemble(entries, cutoff, source_ids, summary)
        if self._token_counter.count(messages) > budget_tokens:
            raise ContextBudgetExceeded("context view exceeds context budget")
        return ContextView(
            messages,
            ContextCompression(
                sources[0].seq,
                sources[-1].seq,
                source_ids,
                summary,
                previous_event_id,
            ),
        )

    @staticmethod
    def _assemble(
        entries: Sequence[_MessageEntry],
        cutoff: int,
        source_ids: Sequence[str],
        summary: str,
    ) -> tuple[Message, ...]:
        source_set = set(source_ids)
        first_source = source_ids[0]
        messages: list[Message] = []
        for index, entry in enumerate(entries):
            if entry.event_id == first_source:
                messages.append(_summary_message(summary))
            if entry.event_id in source_set:
                continue
            if entry.message.pinned or index >= cutoff:
                messages.append(entry.message)
        return tuple(messages)

    @staticmethod
    def _exact_compression(
        events: Sequence[Event], source_ids: tuple[str, ...]
    ) -> tuple[str, Event] | None:
        for event in reversed(events):
            if (
                event.type == "context_compressed"
                and tuple(event.payload["source_event_ids"]) == source_ids
            ):
                return event.payload["summary"], event
        return None

    @staticmethod
    def _previous_compression(
        events: Sequence[Event], source_ids: tuple[str, ...]
    ) -> tuple[Event, tuple[str, ...], str] | None:
        candidates = []
        for event in events:
            if event.type != "context_compressed":
                continue
            previous_ids = tuple(event.payload["source_event_ids"])
            if (
                len(previous_ids) < len(source_ids)
                and source_ids[: len(previous_ids)] == previous_ids
            ):
                candidates.append((event, previous_ids, event.payload["summary"]))
        return max(candidates, key=lambda item: len(item[1]), default=None)
