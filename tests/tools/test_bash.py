import os
import shutil
from pathlib import Path

import pytest

from kernel.core import (
    PermissionGrant,
    ToolCall,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
)
from kernel.tools import register_bash


def find_real_bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    if git:
        root = Path(git).resolve().parent.parent
        candidate = root / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    for candidate in (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Git/bin/bash.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def safe_environment() -> dict[str, str]:
    keys = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "LANG")
    return {key: os.environ[key] for key in keys if key in os.environ}


def context(scope: str, root: Path, bash: str) -> ToolExecutionContext:
    return ToolExecutionContext(
        scope,
        (root,),
        safe_environment(),
        {"bash": bash},
    )


@pytest.mark.skipif(find_real_bash() is None, reason="real Bash is not installed")
def test_real_canary_deletion_is_denied_then_explicitly_allowed(tmp_path: Path) -> None:
    bash = find_real_bash()
    assert bash is not None
    canary = tmp_path / "kernel_canary_file"
    canary.write_text("keep until granted", encoding="utf-8")
    registry = ToolRegistry()
    register_bash(registry)
    registry.freeze()
    call = ToolCall(
        "tc-bash",
        "bash",
        {"command": "rm -- kernel_canary_file", "cwd": str(tmp_path)},
    )

    denied = registry.bind(
        PermissionGrant("denied", workspace_roots=(tmp_path,)),
        context("denied", tmp_path, bash),
    ).dispatch(call)

    assert denied.result["error"]["code"] == "permission_denied"
    assert canary.is_file()

    allowed = registry.bind(
        PermissionGrant(
            "allowed",
            frozenset({ToolPermission.DESTRUCTIVE, ToolPermission.EXECUTE}),
            (tmp_path,),
            frozenset({"bash"}),
        ),
        context("allowed", tmp_path, bash),
    ).dispatch(call)

    assert allowed.result["ok"] is True
    assert allowed.result["value"]["exit_code"] == 0
    assert allowed.result["audit"]["required_permissions"] == [
        "DESTRUCTIVE",
        "EXECUTE",
    ]
    assert not canary.exists()


@pytest.mark.skipif(find_real_bash() is None, reason="real Bash is not installed")
def test_bash_cannot_lower_its_permissions_through_arguments(tmp_path: Path) -> None:
    bash = find_real_bash()
    assert bash is not None
    registry = ToolRegistry()
    register_bash(registry)
    result = registry.bind(
        PermissionGrant("run", workspace_roots=(tmp_path,)),
        context("run", tmp_path, bash),
    ).dispatch(
        ToolCall(
            "tc-bash",
            "bash",
            {"command": "pwd", "permissions": ["READ"]},
        )
    )

    assert result.result["error"]["code"] == "invalid_arguments"
