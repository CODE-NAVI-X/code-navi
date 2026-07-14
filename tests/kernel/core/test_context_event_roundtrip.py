import json

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


def test_s5_adds_exactly_one_event_type_to_the_frozen_s3_set() -> None:
    assert EVENT_TYPES == frozenset(
        {
            "run_started",
            "message_added",
            "tool_called",
            "tool_returned",
            "budget_updated",
            "context_compressed",
            "interrupted",
            "error",
            "run_finished",
        }
    )
