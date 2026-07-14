import copy

import pytest

from kernel.core import (
    ContentBlock,
    Event,
    FatalProviderError,
    Message,
    ProviderResult,
    RetryableProviderError,
)
from kernel.providers import ReplayDivergence, ReplayProvider, ReplayUnavailableError


def text(value: str, *, role: str = "user") -> Message:
    return Message(role, (ContentBlock("text", {"text": value}),))


def event(seq: int, event_type: str, payload: dict) -> Event:
    return Event(
        f"event-{seq}",
        "run-1",
        seq,
        f"2026-07-14T00:00:{seq:02d}Z",
        event_type,
        payload,
    )


def two_call_log() -> tuple[Event, ...]:
    user = text("question")
    first = text("recorded", role="assistant")
    final = text("done", role="assistant")
    return (
        event(0, "run_started", {}),
        event(1, "message_added", {"message": user.to_json()}),
        event(
            2,
            "provider_called",
            {"attempt": 1, "messages": [user.to_json()], "tools": []},
        ),
        event(
            3,
            "provider_returned",
            {
                "attempt": 1,
                "request_event_id": "event-2",
                "request_seq": 2,
                "response": ProviderResult(first).to_json(),
            },
        ),
        event(
            4,
            "provider_called",
            {
                "attempt": 1,
                "messages": [user.to_json(), first.to_json()],
                "tools": [],
            },
        ),
        event(
            5,
            "provider_returned",
            {
                "attempt": 1,
                "request_event_id": "event-4",
                "request_seq": 4,
                "response": ProviderResult(final).to_json(),
            },
        ),
    )


def test_tampered_recorded_response_reports_exact_next_request_field() -> None:
    recorded = list(two_call_log())
    tampered_payload = copy.deepcopy(recorded[3].payload)
    tampered_payload["response"]["message"] = text(
        "tampered", role="assistant"
    ).to_json()
    recorded[3] = event(3, "provider_returned", tampered_payload)
    provider = ReplayProvider(recorded)
    user = text("question")

    tampered = provider.complete([user], tools=[])
    with pytest.raises(ReplayDivergence) as raised:
        provider.complete([user, tampered.message], tools=[])

    divergence = raised.value
    assert isinstance(divergence, FatalProviderError)
    assert divergence.event_index == 4
    assert divergence.event_seq == 4
    assert divergence.path == "/messages/1/content/0/text"
    assert divergence.expected == "recorded"
    assert divergence.actual == "tampered"


def test_exhausted_extra_and_unconsumed_calls_are_divergences() -> None:
    log = two_call_log()
    user = text("question")
    first = text("recorded", role="assistant")
    provider = ReplayProvider(log)

    provider.complete([user], tools=[])
    with pytest.raises(ReplayDivergence) as unconsumed:
        provider.assert_consumed()
    assert unconsumed.value.event_index == 4

    provider.complete([user, first], tools=[])
    provider.assert_consumed()
    with pytest.raises(ReplayDivergence) as extra:
        provider.complete([user, first], tools=[])
    assert extra.value.path == "/provider_called"


def test_recorded_provider_error_is_replayed_without_live_provider() -> None:
    user = text("question")
    log = (
        event(0, "run_started", {}),
        event(
            1,
            "provider_called",
            {"attempt": 1, "messages": [user.to_json()], "tools": []},
        ),
        event(
            2,
            "error",
            {
                "source": "provider",
                "classification": "retryable",
                "message": "busy",
                "attempt": 1,
            },
        ),
    )
    provider = ReplayProvider(log)

    with pytest.raises(RetryableProviderError, match="busy"):
        provider.complete([user], tools=[])
    provider.assert_consumed()


def test_old_s5_log_is_explicitly_not_replayable() -> None:
    old_log = (event(0, "run_started", {}),)

    with pytest.raises(ReplayUnavailableError, match="provider I/O Events are missing"):
        ReplayProvider(old_log)


def test_mixed_s5_prefix_and_s6_suffix_is_not_partially_replayable() -> None:
    user = text("question")
    old_response = text("old response", role="assistant")
    new_response = text("new response", role="assistant")
    mixed_log = (
        event(0, "run_started", {}),
        event(1, "message_added", {"message": user.to_json()}),
        event(
            2,
            "budget_updated",
            {
                "used_steps": 1,
                "max_steps": 3,
                "used_tool_calls": 0,
                "max_tool_calls": 0,
            },
        ),
        event(3, "message_added", {"message": old_response.to_json()}),
        event(
            4,
            "provider_called",
            {
                "attempt": 1,
                "messages": [user.to_json(), old_response.to_json()],
                "tools": [],
            },
        ),
        event(
            5,
            "provider_returned",
            {
                "attempt": 1,
                "request_event_id": "event-4",
                "request_seq": 4,
                "response": ProviderResult(new_response).to_json(),
            },
        ),
    )

    with pytest.raises(ReplayUnavailableError, match="complete provider I/O Events"):
        ReplayProvider(mixed_log)
