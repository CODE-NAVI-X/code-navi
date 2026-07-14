"""Deterministic provider replay from a recorded kernel Event log."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from kernel.core.types import (
    Event,
    FatalProviderError,
    Message,
    ProviderResult,
    RetryableProviderError,
)

_MISSING = "<missing>"


class ReplayUnavailableError(ValueError):
    """A valid Event log lacks the provider I/O required for replay."""


class ReplayDivergence(FatalProviderError):
    """The replayed provider request differs from the recorded request."""

    def __init__(
        self,
        *,
        event_index: int,
        event_seq: int,
        path: str,
        expected: Any,
        actual: Any,
        expected_request: Mapping[str, Any] | None = None,
        actual_request: Mapping[str, Any] | None = None,
    ) -> None:
        self.event_index = event_index
        self.event_seq = event_seq
        self.path = path
        self.expected = expected
        self.actual = actual
        self.expected_request = (
            None if expected_request is None else dict(expected_request)
        )
        self.actual_request = None if actual_request is None else dict(actual_request)
        expected_text = json.dumps(expected, ensure_ascii=False, default=str)
        actual_text = json.dumps(actual, ensure_ascii=False, default=str)
        super().__init__(
            f"replay divergence at Event index {event_index}, seq {event_seq}, "
            f"path {path}: expected {expected_text}, actual {actual_text}"
        )


@dataclass(frozen=True, slots=True)
class _RecordedProviderCall:
    event_index: int
    event_seq: int
    request: dict[str, Any]
    response: dict[str, Any] | None = None
    error_classification: str | None = None
    error_message: str | None = None


def first_structural_difference(
    expected: Any, actual: Any, path: str = ""
) -> tuple[str, Any, Any] | None:
    """Return the first JSON-structural difference without canonicalizing data."""
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return path or "/", expected, actual
        for key in expected:
            child_path = f"{path}/{_pointer_token(str(key))}"
            if key not in actual:
                return child_path, expected[key], _MISSING
            difference = first_structural_difference(
                expected[key], actual[key], child_path
            )
            if difference is not None:
                return difference
        for key in actual:
            if key not in expected:
                return f"{path}/{_pointer_token(str(key))}", _MISSING, actual[key]
        return None
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return path or "/", expected, actual
        common = min(len(expected), len(actual))
        for index in range(common):
            difference = first_structural_difference(
                expected[index], actual[index], f"{path}/{index}"
            )
            if difference is not None:
                return difference
        if len(expected) > common:
            return f"{path}/{common}", expected[common], _MISSING
        if len(actual) > common:
            return f"{path}/{common}", _MISSING, actual[common]
        return None
    if type(expected) is not type(actual) or expected != actual:
        return path or "/", expected, actual
    return None


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


class ReplayProvider:
    """Serve normalized provider outcomes from recorded provider Events."""

    supports_streaming = False
    max_context: int | None = None

    def __init__(self, recorded_log: Sequence[Event]) -> None:
        self._events = tuple(recorded_log)
        self._calls = self._parse_calls(self._events)
        self._position = 0

    @property
    def consumed_calls(self) -> int:
        return self._position

    @property
    def total_calls(self) -> int:
        return len(self._calls)

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]] | None = None,
    ) -> ProviderResult:
        actual_request = {
            "messages": [message.to_json() for message in messages],
            "tools": [dict(tool) for tool in (tools or ())],
        }
        if self._position >= len(self._calls):
            event_seq = self._events[-1].seq + 1 if self._events else 0
            raise ReplayDivergence(
                event_index=len(self._events),
                event_seq=event_seq,
                path="/provider_called",
                expected=_MISSING,
                actual=actual_request,
                actual_request=actual_request,
            )
        recorded = self._calls[self._position]
        difference = first_structural_difference(recorded.request, actual_request)
        if difference is not None:
            path, expected, actual = difference
            raise ReplayDivergence(
                event_index=recorded.event_index,
                event_seq=recorded.event_seq,
                path=path,
                expected=expected,
                actual=actual,
                expected_request=recorded.request,
                actual_request=actual_request,
            )
        self._position += 1
        if recorded.response is not None:
            return ProviderResult.from_json(recorded.response)
        if recorded.error_classification == "retryable":
            raise RetryableProviderError(recorded.error_message or "")
        raise FatalProviderError(recorded.error_message or "")

    def assert_consumed(self) -> None:
        """Raise when replay ended before consuming every recorded provider call."""
        if self._position == len(self._calls):
            return
        recorded = self._calls[self._position]
        raise ReplayDivergence(
            event_index=recorded.event_index,
            event_seq=recorded.event_seq,
            path="/provider_called",
            expected=recorded.request,
            actual=_MISSING,
            expected_request=recorded.request,
        )

    @staticmethod
    def _parse_calls(events: Sequence[Event]) -> tuple[_RecordedProviderCall, ...]:
        calls: list[_RecordedProviderCall] = []
        previous_steps = 0
        for index, event in enumerate(events):
            previous = events[index - 1] if index > 0 else None
            if event.type == "error" and event.payload.get("source") == "provider":
                if previous is None or previous.type != "provider_called":
                    raise ReplayUnavailableError(
                        f"provider error at Event index {index} lacks its "
                        "provider_called Event; provider I/O history is incomplete"
                    )
            if event.type == "budget_updated":
                used_steps = event.payload["used_steps"]
                if used_steps > previous_steps and (
                    previous is None or previous.type != "provider_returned"
                ):
                    raise ReplayUnavailableError(
                        f"provider step at Event index {index} lacks its complete "
                        "provider I/O Events"
                    )
                previous_steps = used_steps
            if event.type == "provider_returned":
                if previous is None or previous.type != "provider_called":
                    raise ReplayUnavailableError(
                        f"provider_returned at Event index {index} has no "
                        "preceding provider_called Event"
                    )
                continue
            if event.type != "provider_called":
                continue
            if index + 1 >= len(events):
                raise ReplayUnavailableError(
                    f"provider_called at Event index {index} has no recorded outcome"
                )
            request = {
                "messages": list(event.payload["messages"]),
                "tools": list(event.payload["tools"]),
            }
            outcome = events[index + 1]
            if outcome.type == "provider_returned":
                if (
                    outcome.payload["attempt"] != event.payload["attempt"]
                    or outcome.payload["request_event_id"] != event.event_id
                    or outcome.payload["request_seq"] != event.seq
                ):
                    raise ReplayUnavailableError(
                        f"provider_returned at Event index {index + 1} does not "
                        "reference its provider_called Event"
                    )
                calls.append(
                    _RecordedProviderCall(
                        index,
                        event.seq,
                        request,
                        response=dict(outcome.payload["response"]),
                    )
                )
                continue
            if outcome.type == "error" and outcome.payload.get("source") == "provider":
                if outcome.payload.get("attempt") != event.payload["attempt"]:
                    raise ReplayUnavailableError(
                        f"provider error at Event index {index + 1} has wrong attempt"
                    )
                calls.append(
                    _RecordedProviderCall(
                        index,
                        event.seq,
                        request,
                        error_classification=outcome.payload["classification"],
                        error_message=outcome.payload["message"],
                    )
                )
                continue
            raise ReplayUnavailableError(
                f"provider_called at Event index {index} must be followed by "
                "provider_returned or a provider error"
            )
        if not calls:
            raise ReplayUnavailableError(
                "recorded log is not replayable: complete provider I/O Events are missing"
            )
        return tuple(calls)
