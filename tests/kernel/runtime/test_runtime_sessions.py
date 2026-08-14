from pathlib import Path

import pytest

from kernel.adapters.jsonl_session import load_session
from kernel.core import AgentState, ContentBlock, Message, ProviderResult
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest


def _assistant(text: str) -> Message:
    return Message("assistant", (ContentBlock("text", {"text": text}),))


def test_runtime_persists_event_only_session_logs(tmp_path: Path) -> None:
    runtime = AgentRuntime(
        MockProvider([ProviderResult(_assistant("saved"))]), session_dir=tmp_path
    )
    result = runtime.run(
        AgentSpec("helper", "Helps.", "Help."),
        RuntimeRequest("go", session_id="session-a", run_id="run-a"),
    )

    path = Path(result.event_log_path or "")
    assert path == tmp_path / "session-a" / "run-a.jsonl"
    assert path.exists()
    assert load_session(path) == result.events
    assert AgentState.fold(load_session(path)) == result.run_result.state
    raw = path.read_text(encoding="utf-8")
    for forbidden in (
        "PermissionGrant",
        "destructive_tool_names",
        "workspace_roots",
        "allowed_permissions",
    ):
        assert forbidden not in raw


def test_runtime_keeps_distinct_run_files_for_one_session(tmp_path: Path) -> None:
    provider = MockProvider([ProviderResult(_assistant("one")), ProviderResult(_assistant("two"))])
    runtime = AgentRuntime(provider, session_dir=tmp_path)
    agent = AgentSpec("helper", "Helps.", "Help.")
    first = runtime.run(agent, RuntimeRequest("one", session_id="shared", run_id="run-1"))
    second = runtime.run(agent, RuntimeRequest("two", session_id="shared", run_id="run-2"))

    assert first.event_log_path != second.event_log_path
    assert Path(first.event_log_path or "").exists()
    assert Path(second.event_log_path or "").exists()
    assert [message["role"] for message in provider.calls[1]["messages"]] == ["system", "user"]


def test_runtime_uses_only_explicit_history_on_a_later_run(tmp_path: Path) -> None:
    provider = MockProvider(
        [ProviderResult(_assistant("first")), ProviderResult(_assistant("second"))]
    )
    runtime = AgentRuntime(provider, session_dir=tmp_path)
    agent = AgentSpec("helper", "Helps.", "Help.")
    runtime.run(agent, RuntimeRequest("one", session_id="shared", run_id="run-1"))
    history = (
        Message("user", (ContentBlock("text", {"text": "one"}),)),
        _assistant("first"),
    )

    runtime.run(
        agent,
        RuntimeRequest(
            "two",
            session_id="different-runtime-session",
            run_id="run-2",
            conversation_history=history,
        ),
    )

    sent = provider.calls[1]["messages"]
    assert sent[1:3] == [message.to_json() for message in history]
    assert sent[0]["metadata"]["session_id"] == "different-runtime-session"


@pytest.mark.parametrize(
    "session_id, run_id",
    [
        ("../escape", "run"),
        ("session", "../escape"),
        ("session/child", "run"),
        ("session", "run\\child"),
    ],
)
def test_runtime_rejects_session_path_traversal(
    tmp_path: Path, session_id: str, run_id: str
) -> None:
    runtime = AgentRuntime(MockProvider([]), session_dir=tmp_path)
    with pytest.raises(ValueError, match="safe path segment"):
        runtime.run(
            AgentSpec("helper", "Helps.", "Help."),
            RuntimeRequest("go", session_id=session_id, run_id=run_id),
        )
