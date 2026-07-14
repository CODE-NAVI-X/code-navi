from pathlib import Path

import pytest

from kernel.adapters.jsonl_session import (
    SessionConflictError,
    SessionFormatError,
    load_session,
    save_session,
)
from kernel.core import (
    AgentState,
    ContentBlock,
    Event,
    KernelConfig,
    Message,
    PermissionGrant,
    ProviderResult,
    TailWithSummary,
    ToolCall,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    run,
)
from kernel.providers import MockProvider


class UnitCounter:
    def count(self, messages) -> int:
        return len(messages)


class Summarizer:
    def __init__(self) -> None:
        self.calls = 0

    def summarize(self, messages, budget_tokens: int) -> str:
        self.calls += 1
        return f"summary-{self.calls}"


class Dispatcher:
    def provider_tools(self):
        return ()

    def dispatch(self, call: ToolCall) -> ToolResult:
        return ToolResult(call.id, call.name, {"ok": True})


def event(seq: int, event_type: str, payload: dict) -> Event:
    return Event(
        f"e{seq}",
        "run-1",
        seq,
        f"2026-07-14T00:00:{seq:02d}Z",
        event_type,
        payload,
    )


def text(text: str, *, pinned: bool = False, role: str = "user") -> Message:
    return Message(
        role,
        (ContentBlock("text", {"text": text}),),
        pinned=pinned,
    )


def seed_events() -> tuple[Event, ...]:
    messages = (
        text("constraint", pinned=True),
        text("old-1"),
        text("old-2"),
        text("recent"),
    )
    return (event(0, "run_started", {}),) + tuple(
        event(index, "message_added", {"message": item.to_json()})
        for index, item in enumerate(messages, start=1)
    )


def tool_message() -> Message:
    call = ToolCall("tc-1", "lookup", {"q": "x"})
    return Message(
        "assistant",
        (ContentBlock("tool_use", {"tool_call": call.to_json()}),),
    )


def test_save_appends_only_the_missing_suffix(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    events = seed_events()

    save_session(path, events[:2])
    original_prefix = path.read_bytes()
    save_session(path, events)

    assert path.read_bytes().startswith(original_prefix)
    assert load_session(path) == events
    assert "AgentState" not in path.read_text(encoding="utf-8")
    assert "PermissionGrant" not in path.read_text(encoding="utf-8")


def test_save_rejects_overwrite_or_fork(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    events = seed_events()
    save_session(path, events)
    fork = list(events)
    fork[2] = Event(
        "forked",
        "run-1",
        2,
        "2026-07-14T00:00:02Z",
        "message_added",
        {"message": text("different").to_json()},
    )

    with pytest.raises(SessionConflictError, match="prefix"):
        save_session(path, fork)
    with pytest.raises(SessionConflictError, match="truncate"):
        save_session(path, events[:-1])


@pytest.mark.parametrize(
    "contents",
    [
        '{"event_id":"broken"}',
        '{"event_id":"e0","run_id":"r","seq":0,"timestamp":"t","type":"run_started","payload":{}}',
        '\n'.join(
            [
                '{"event_id":"e0","run_id":"r","seq":0,"timestamp":"t","type":"run_started","payload":{}}',
                '{"event_id":"e2","run_id":"r","seq":2,"timestamp":"t","type":"run_finished","payload":{"status":"completed","reason":"completed"}}',
            ]
        )
        + "\n",
    ],
)
def test_load_strictly_rejects_malformed_or_unordered_jsonl(
    tmp_path: Path, contents: str
) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(SessionFormatError):
        load_session(path)


def test_save_rejects_out_of_order_compression_sources(tmp_path: Path) -> None:
    messages = seed_events()
    invalid = Event(
        "compressed-out-of-order",
        "run-1",
        5,
        "2026-07-14T00:00:05Z",
        "context_compressed",
        {
            "start_seq": 2,
            "end_seq": 3,
            "source_event_ids": ["e2", "e4", "e3"],
            "summary": "invalid order",
            "previous_event_id": None,
        },
    )

    with pytest.raises(SessionFormatError, match="sequence order"):
        save_session(tmp_path / "invalid-compression.jsonl", (*messages, invalid))


def test_save_load_resume_matches_uninterrupted_without_duplicate_compression(
    tmp_path: Path,
) -> None:
    initial = seed_events()
    final_message = text("done", role="assistant")
    uninterrupted = run(
        MockProvider(
            [ProviderResult(tool_message()), ProviderResult(final_message)]
        ),
        Dispatcher(),
        [],
        KernelConfig(max_steps=2, max_tool_calls=2),
        prior_events=initial,
        context_policy=TailWithSummary(
            UnitCounter(), Summarizer(), summary_budget_tokens=1
        ),
        context_budget_tokens=3,
    )
    first_tool_message_index = next(
        index
        for index, item in enumerate(uninterrupted.events)
        if item.type == "message_added"
        and Message.from_json(item.payload["message"]).role == "tool"
    )
    safe_prefix = uninterrupted.events[: first_tool_message_index + 1]
    path = tmp_path / "resume.jsonl"
    save_session(path, safe_prefix)

    loaded = load_session(path)
    resumed = run(
        MockProvider([ProviderResult(final_message)]),
        Dispatcher(),
        [],
        KernelConfig(max_steps=2, max_tool_calls=2),
        prior_events=loaded,
        context_policy=TailWithSummary(
            UnitCounter(), Summarizer(), summary_budget_tokens=1
        ),
        context_budget_tokens=3,
    )
    save_session(path, resumed.events)

    assert AgentState.fold(load_session(path)) == uninterrupted.state
    source_ranges = [
        tuple(item.payload["source_event_ids"])
        for item in resumed.events
        if item.type == "context_compressed"
    ]
    assert len(source_ranges) == len(set(source_ranges))


def test_resume_requires_a_fresh_permission_grant(tmp_path: Path) -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "execute",
            "Execute a test action.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            frozenset({ToolPermission.EXECUTE}),
        ),
        lambda args, context: calls.append(context.run_scope) or "ok",
    )
    first_call = ToolCall("tc-allowed", "execute", {})
    first = run(
        MockProvider(
            [
                ProviderResult(
                    Message(
                        "assistant",
                        (
                            ContentBlock(
                                "tool_use", {"tool_call": first_call.to_json()}
                            ),
                        ),
                    )
                )
            ]
        ),
        registry.bind(
            PermissionGrant(
                "permission-run", frozenset({ToolPermission.EXECUTE})
            ),
            ToolExecutionContext("permission-run"),
        ),
        [text("go")],
        KernelConfig(max_steps=1, max_tool_calls=2),
    )
    safe_end = max(
        index
        for index, item in enumerate(first.events)
        if item.type == "message_added"
        and Message.from_json(item.payload["message"]).role == "tool"
    )
    path = tmp_path / "permissions.jsonl"
    save_session(path, first.events[: safe_end + 1])
    serialized = path.read_text(encoding="utf-8")

    second_call = ToolCall("tc-denied", "execute", {})
    resumed = run(
        MockProvider(
            [
                ProviderResult(
                    Message(
                        "assistant",
                        (
                            ContentBlock(
                                "tool_use", {"tool_call": second_call.to_json()}
                            ),
                        ),
                    )
                ),
                ProviderResult(text("done", role="assistant")),
            ]
        ),
        registry.bind(
            PermissionGrant("permission-run"),
            ToolExecutionContext("permission-run"),
        ),
        [],
        KernelConfig(max_steps=3, max_tool_calls=3),
        prior_events=load_session(path),
    )

    returned = [
        item.payload["tool_result"]
        for item in resumed.events
        if item.type == "tool_returned"
    ]
    assert calls == ["permission-run"]
    assert returned[-1]["result"]["error"]["code"] == "permission_denied"
    assert "allowed_permissions" not in serialized
    assert "destructive_tool_names" not in serialized
