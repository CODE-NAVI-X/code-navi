"""Strict append-only JSONL persistence for kernel Event logs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from kernel.core.types import AgentState, Event, Message

_EVENT_KEYS = frozenset(
    {"event_id", "run_id", "seq", "timestamp", "type", "payload"}
)


class SessionFormatError(ValueError):
    """A session is not a strict, foldable Event JSONL log."""


class SessionConflictError(RuntimeError):
    """A save would overwrite, truncate, or fork an existing Event log."""


def save_session(path: str | Path, events: Sequence[Event]) -> None:
    """Append only the suffix missing after an existing complete Event prefix."""
    target = Path(path)
    proposed = tuple(events)
    _validate_event_sequence(proposed)
    existing = load_session(target) if target.exists() else ()
    if len(existing) > len(proposed):
        raise SessionConflictError("save would truncate the existing Event log")
    if proposed[: len(existing)] != existing:
        raise SessionConflictError("existing Event log is not a complete prefix")
    suffix = proposed[len(existing) :]
    if not suffix:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        for event in suffix:
            stream.write(
                json.dumps(
                    event.to_json(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_session(path: str | Path) -> tuple[Event, ...]:
    """Load, strictly validate, and fold-check a JSONL Event log."""
    target = Path(path)
    raw = target.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise SessionFormatError("non-empty JSONL session must end with a newline")
    try:
        contents = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SessionFormatError("session must be valid UTF-8") from exc
    events: list[Event] = []
    for line_number, line in enumerate(contents.splitlines(), start=1):
        if not line:
            raise SessionFormatError(f"blank JSONL line at {line_number}")
        try:
            data = json.loads(line)
            _validate_event_object(data)
            event = Event.from_json(data)
            encoded = json.loads(json.dumps(event.to_json()))
            if Event.from_json(encoded) != event:
                raise SessionFormatError(
                    f"Event round-trip failed at line {line_number}"
                )
        except SessionFormatError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SessionFormatError(
                f"invalid Event JSON at line {line_number}"
            ) from exc
        events.append(event)
    result = tuple(events)
    _validate_event_sequence(result)
    return result


def _validate_event_object(data: Any) -> None:
    if not isinstance(data, Mapping) or frozenset(data) != _EVENT_KEYS:
        raise SessionFormatError("Event JSON must contain exactly the common envelope")
    for key in ("event_id", "run_id", "timestamp", "type"):
        if not isinstance(data[key], str) or not data[key]:
            raise SessionFormatError(f"Event {key} must be a non-empty string")
    if not isinstance(data["seq"], int) or isinstance(data["seq"], bool):
        raise SessionFormatError("Event seq must be int")
    if not isinstance(data["payload"], Mapping):
        raise SessionFormatError("Event payload must be an object")


def _validate_event_sequence(events: Sequence[Event]) -> None:
    if not events:
        AgentState.fold(events)
        return
    if events[0].type != "run_started":
        raise SessionFormatError("session must start with run_started")
    if events[0].seq != 0:
        raise SessionFormatError("session must start at Event seq 0")
    run_id = events[0].run_id
    event_ids: set[str] = set()
    previous_seq = events[0].seq - 1
    prior_events: dict[str, Event] = {}
    message_events: dict[str, Event] = {}
    for event in events:
        if event.run_id != run_id:
            raise SessionFormatError("all Events in a session must share run_id")
        if event.event_id in event_ids:
            raise SessionFormatError("Event ids must be unique")
        if event.seq != previous_seq + 1:
            raise SessionFormatError("Event seq values must be contiguous and ordered")
        if event.type == "context_compressed":
            _validate_compression_references(event, prior_events, message_events)
        event_ids.add(event.event_id)
        prior_events[event.event_id] = event
        if event.type == "message_added":
            message_events[event.event_id] = event
        previous_seq = event.seq
    try:
        AgentState.fold(events)
    except (KeyError, TypeError, ValueError) as exc:
        raise SessionFormatError("Event log cannot be folded into AgentState") from exc


def _validate_compression_references(
    event: Event,
    prior_events: Mapping[str, Event],
    message_events: Mapping[str, Event],
) -> None:
    payload = event.payload
    source_ids = tuple(payload["source_event_ids"])
    try:
        sources = tuple(message_events[event_id] for event_id in source_ids)
    except KeyError as exc:
        raise SessionFormatError(
            "context_compressed sources must reference earlier message_added Events"
        ) from exc
    if any(Message.from_json(item.payload["message"]).pinned for item in sources):
        raise SessionFormatError("context_compressed must not summarize pinned messages")
    if any(left.seq >= right.seq for left, right in zip(sources, sources[1:])):
        raise SessionFormatError(
            "context_compressed sources must be in Event sequence order"
        )
    if payload["start_seq"] != sources[0].seq or payload["end_seq"] != sources[-1].seq:
        raise SessionFormatError("context_compressed seq range must match its sources")
    previous_id = payload.get("previous_event_id")
    if previous_id is None:
        return
    previous = prior_events.get(previous_id)
    if previous is None or previous.type != "context_compressed":
        raise SessionFormatError(
            "previous_event_id must reference an earlier context_compressed Event"
        )
    previous_ids = tuple(previous.payload["source_event_ids"])
    if source_ids[: len(previous_ids)] != previous_ids or len(previous_ids) >= len(
        source_ids
    ):
        raise SessionFormatError("rolling compression must extend its previous source range")
