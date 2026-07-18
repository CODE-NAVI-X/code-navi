import json

import pytest

from kernel.core import AgentState, ContentBlock, Event, Message
from kernel.core.types import EVENT_TYPES


def test_context_compressed_event_json_round_trips() -> None:
    event = Event(
        "ce-1",
        "run-1",
        8,
        "2026-07-14T00:00:08Z",
        "context_compressed",
        {
            "start_seq": 1,
            "end_seq": 5,
            "source_event_ids": ["m1", "m3", "m5"],
            "summary": "facts preserved",
            "previous_event_id": None,
        },
    )

    encoded = json.loads(json.dumps(event.to_json()))

    assert Event.from_json(encoded) == event


def test_message_pinned_flag_json_round_trips() -> None:
    message = Message(
        "user",
        (ContentBlock("text", {"text": "keep verbatim"}),),
        {"source": "host"},
        pinned=True,
    )

    encoded = json.loads(json.dumps(message.to_json()))

    assert Message.from_json(encoded) == message


def test_agent_state_fold_ignores_context_compressed_view_event() -> None:
    message_event = Event(
        "m1",
        "run-1",
        0,
        "2026-07-14T00:00:00Z",
        "message_added",
        {"message": Message("user").to_json()},
    )
    compression_event = Event(
        "ce-1",
        "run-1",
        1,
        "2026-07-14T00:00:01Z",
        "context_compressed",
        {
            "start_seq": 0,
            "end_seq": 0,
            "source_event_ids": ["m1"],
            "summary": "summary",
            "previous_event_id": None,
        },
    )

    state = AgentState.fold((message_event, compression_event))

    assert state.messages == (Message("user"),)
    assert state.last_seq == 1


def test_agent_state_fold_ignores_provider_audit_events() -> None:
    message = Message("user")
    response = Message("assistant")
    events = (
        Event(
            "call-1",
            "run-1",
            0,
            "2026-07-14T00:00:00Z",
            "provider_called",
            {"attempt": 1, "messages": [message.to_json()], "tools": []},
        ),
        Event(
            "return-1",
            "run-1",
            1,
            "2026-07-14T00:00:01Z",
            "provider_returned",
            {
                "attempt": 1,
                "request_event_id": "call-1",
                "request_seq": 0,
                "response": {
                    "message": response.to_json(),
                    "usage": {},
                    "finish_reason": "stop",
                    "metadata": {},
                },
            },
        ),
    )

    encoded = json.loads(json.dumps([item.to_json() for item in events]))
    decoded = tuple(Event.from_json(item) for item in encoded)
    state = AgentState.fold(decoded)

    assert decoded == events
    assert state.messages == ()
    assert state.steps_used == 0
    assert state.last_seq == 1


def test_provider_events_reject_fields_outside_normalized_io_contract() -> None:
    with pytest.raises(ValueError, match="requires exactly"):
        Event(
            "call-1",
            "run-1",
            0,
            "2026-07-14T00:00:00Z",
            "provider_called",
            {
                "attempt": 1,
                "messages": [],
                "tools": [],
                "permission_grant": {"allowed": ["PUBLISH"]},
            },
        )


def test_s6_adds_exactly_two_provider_event_types_to_the_frozen_set() -> None:
    assert EVENT_TYPES == frozenset(
        {
            "run_started",
            "message_added",
            "tool_called",
            "tool_returned",
            "budget_updated",
            "context_compressed",
            "provider_called",
            "provider_returned",
            "interrupted",
            "error",
            "run_finished",
        }
    )
