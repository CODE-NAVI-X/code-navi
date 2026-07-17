import json
from pathlib import Path

import pytest

from code_navi.context import (
    ContextBuilder,
    ContextError,
    ConversationTurn,
    discover_project_root,
)


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\nA learning project.\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text(
        "first = 1\nsecond = 2\nthird = 3\n",
        encoding="utf-8",
    )
    task_dir = root / ".code-navi"
    task_dir.mkdir()
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "title": "Demo course project",
                "goal": "Understand the parser",
                "current_milestone": "Debugging",
                "active_files": ["src/main.py"],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_discover_project_root_from_nested_directory(tmp_path: Path) -> None:
    root = make_project(tmp_path)

    assert discover_project_root(root / "src") == root


def test_prepare_question_resolves_bounded_context_anchors(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    builder = ContextBuilder(root)

    prepared = builder.prepare(
        "@last @src/main.py:2-3 为什么这样写？",
        last_answer="上一轮解释",
        branch_history=(ConversationTurn("先问", "先答"),),
    )

    assert prepared.question == "为什么这样写？"
    assert prepared.context.task.current_milestone == "Debugging"
    assert prepared.context.snippets[0].text == "second = 2\nthird = 3"
    assert prepared.context.previous_answer == "上一轮解释"
    assert prepared.context.sources == (
        "task.json",
        "README.md",
        "src/main.py",
        "上一条回答",
        "问题分支",
    )
    assert "User question:\n为什么这样写？" in prepared.runtime_input()


def test_prepare_rejects_missing_last_answer_and_outside_files(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("secret = True\n", encoding="utf-8")
    builder = ContextBuilder(root)

    with pytest.raises(ContextError, match="no previous answer"):
        builder.prepare("@last 解释它")
    with pytest.raises(ContextError, match="outside the project"):
        builder.prepare("解释它", attachments=(str(outside),))


def test_no_project_context_keeps_explicit_file_attachment(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    builder = ContextBuilder(root, include_project_context=False)

    prepared = builder.prepare("解释", attachments=("src/main.py:1-1",))

    assert prepared.context.task.title is None
    assert prepared.context.project_summary is None
    assert prepared.context.sources == ("src/main.py",)
