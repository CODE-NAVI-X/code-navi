import io
import json
from pathlib import Path

from code_navi.application import QuestionService
from code_navi.cli import EXIT_OK, InteractiveShell, main
from code_navi.context import ContextBuilder
from code_navi.providers import OfflineProvider


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='project'\n", encoding="utf-8")
    (root / "README.md").write_text("# Project context\n", encoding="utf-8")
    return root


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
        service,
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
    assert stderr.getvalue() == ""
    assert len(provider.calls) == 3
    branch_user_message = provider.calls[1]["messages"][-1]["content"][0]["text"]
    assert "Previous assistant answer:" in branch_user_message
    final_user_message = provider.calls[-1]["messages"][-1]["content"][0]["text"]
    assert "Temporary question branch history:" in final_user_message
    assert len(list((root / "events").rglob("*.jsonl"))) == 3
