import io
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import code_navi.cli as cli_module
from code_navi.application import QuestionService
from code_navi.cli import EXIT_OK, EXIT_USAGE, InteractiveShell, main
from code_navi.cli_conversation import (
    CliConversationNotFoundError,
    CliConversationScopeError,
    CliConversationStore,
    ShellConversationService,
)
from code_navi.context import ContextBuilder
from code_navi.db import Base
from code_navi.providers import OfflineProvider


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='project'\n", encoding="utf-8")
    (root / "README.md").write_text("# Project context\n", encoding="utf-8")
    return root


def make_store(tmp_path: Path) -> CliConversationStore:
    database = create_engine(f"sqlite:///{tmp_path / 'cli-conversations.db'}")
    Base.metadata.create_all(database)
    return CliConversationStore(sessionmaker(bind=database, expire_on_commit=False))


def test_one_shot_cli_uses_project_context_and_persists_events(
    tmp_path: Path, capsys: object
) -> None:
    root = make_project(tmp_path)

    exit_code = main(
        [
            "ask",
            "这个项目是什么？",
            "--project",
            str(root),
            "--provider",
            "mock",
            "--mock-response",
            "离线回答",
        ]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == EXIT_OK
    assert captured.out == "离线回答\n"
    assert "context: project · README.md" in captured.err
    assert len(list((root / "var" / "runs").rglob("*.jsonl"))) == 1


def test_one_shot_json_output_is_machine_readable(tmp_path: Path, capsys: object) -> None:
    root = make_project(tmp_path)

    exit_code = main(
        [
            "ask",
            "解释当前项目",
            "--project",
            str(root),
            "--provider",
            "mock",
            "--mock-response",
            "answer",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert exit_code == EXIT_OK
    assert payload["schema_version"] == 1
    assert payload["status"] == "completed"
    assert payload["context"]["sources"] == ["README.md"]
    assert payload["output"] == "answer"


def test_cli_ignores_research_only_deepseek_environment(
    tmp_path: Path, capsys: object, monkeypatch: object
) -> None:
    root = make_project(tmp_path)
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")  # type: ignore[attr-defined]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")  # type: ignore[attr-defined]

    exit_code = main(
        [
            "ask",
            "解释当前项目",
            "--project",
            str(root),
            "--mock-response",
            "CLI 仍使用离线模式",
        ]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == EXIT_OK
    assert captured.out == "CLI 仍使用离线模式\n"


def test_interactive_shell_supports_quick_questions_and_focus_branch(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path)
    provider = OfflineProvider("shell answer")
    service = QuestionService(
        provider,
        ContextBuilder(root),
        events_dir=root / "events",
        session_id="shell-test",
    )
    store = make_store(tmp_path)
    shell_service = ShellConversationService(service, store, store.create(root))
    stdin = io.StringIO(
        "? 第一个问题\n"
        "/branch 深入问题\n"
        "继续追问\n"
        "/context\n"
        "/back\n"
        "/exit\n"
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = InteractiveShell(
        shell_service,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    ).run()

    output = stdout.getvalue()
    assert exit_code == EXIT_OK
    assert "[project] > " in output
    assert "[project › 深入问题] > " in output
    assert "问题分支：深入问题" in output
    assert "已返回主任务" in output
    assert "conversation_id:" in output
    assert stderr.getvalue() == ""
    assert len(provider.calls) == 3
    branch_messages = provider.calls[1]["messages"]
    assert [message["role"] for message in branch_messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert branch_messages[2]["content"][0]["text"] == "shell answer"
    final_user_message = provider.calls[-1]["messages"][-1]["content"][0]["text"]
    assert "Temporary question branch history:" in final_user_message
    assert len(list((root / "events").rglob("*.jsonl"))) == 3
    restored = store.load(shell_service.conversation_id, root)
    assert len(restored.messages) == 2


def test_shell_main_conversation_is_continuous_and_resumable_after_service_rebuild(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path)
    store = make_store(tmp_path)
    state = store.create(root)
    first_provider = OfflineProvider("first answer")
    first = ShellConversationService(
        QuestionService(
            first_provider,
            ContextBuilder(root),
            events_dir=root / "events",
            session_id="runtime-session-first",
        ),
        store,
        state,
    )
    first.ask_main("first question")

    second_provider = OfflineProvider("second answer")
    rebuilt = ShellConversationService(
        QuestionService(
            second_provider,
            ContextBuilder(root),
            events_dir=root / "events",
            session_id="runtime-session-second",
        ),
        store,
        store.load(state.conversation_id, root),
    )
    assert rebuilt.last_answer == "first answer"
    rebuilt.ask_main("second question")

    sent = second_provider.calls[0]["messages"]
    assert [message["role"] for message in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"][0]["text"] == "first question"
    assert sent[2]["content"][0]["text"] == "first answer"
    assert sent[0]["metadata"]["session_id"] == "runtime-session-second"
    assert rebuilt.conversation_id == state.conversation_id
    assert rebuilt.conversation_id != "runtime-session-second"
    assert len(store.load(state.conversation_id, root).messages) == 4


def test_cli_conversation_store_rejects_unknown_and_wrong_project_scope(
    tmp_path: Path,
) -> None:
    first_project = make_project(tmp_path / "first")
    second_project = make_project(tmp_path / "second")
    store = make_store(tmp_path)
    state = store.create(first_project)

    with pytest.raises(CliConversationNotFoundError):
        store.load("missing", first_project)
    with pytest.raises(CliConversationScopeError):
        store.load(state.conversation_id, second_project)


def test_shell_resume_interface_is_explicit_and_project_scoped(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    root = make_project(tmp_path)
    database = create_engine(f"sqlite:///{tmp_path / 'resume.db'}")
    Base.metadata.create_all(database)
    factory = sessionmaker(bind=database, expire_on_commit=False)
    state = CliConversationStore(factory).create(root)
    monkeypatch.setattr(cli_module, "SessionLocal", factory)  # type: ignore[attr-defined]
    monkeypatch.setattr(sys, "stdin", io.StringIO("/exit\n"))  # type: ignore[attr-defined]

    resumed = main(
        [
            "shell",
            "--resume",
            state.conversation_id,
            "--project",
            str(root),
            "--provider",
            "mock",
        ]
    )
    missing = main(
        [
            "shell",
            "--resume",
            "missing",
            "--project",
            str(root),
            "--provider",
            "mock",
        ]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert resumed == EXIT_OK
    assert state.conversation_id in captured.out
    assert missing == EXIT_USAGE
    assert "CLI conversation not found: missing" in captured.err


def test_one_shot_question_service_remains_stateless(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    provider = OfflineProvider("answer")
    service = QuestionService(provider, ContextBuilder(root), events_dir=root / "events")

    service.ask("first")
    service.ask("second")

    assert [message["role"] for message in provider.calls[1]["messages"]] == [
        "system",
        "user",
    ]


def test_shell_history_keeps_complete_recent_turns_inside_the_context_budget(
    tmp_path: Path,
) -> None:
    root = make_project(tmp_path)
    store = make_store(tmp_path)
    state = store.create(root)
    state = store.append_turn(
        state.conversation_id,
        root,
        "old user " + ("x" * 100),
        "old assistant " + ("y" * 100),
    )
    state = store.append_turn(state.conversation_id, root, "recent user", "recent answer")
    provider = OfflineProvider("next answer")
    shell = ShellConversationService(
        QuestionService(
            provider,
            ContextBuilder(root, include_project_context=False, max_context_chars=80),
            events_dir=root / "events",
        ),
        store,
        state,
    )

    shell.ask_main("next question")

    sent = provider.calls[0]["messages"]
    assert [message["role"] for message in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"][0]["text"] == "recent user"
    assert sent[2]["content"][0]["text"] == "recent answer"
