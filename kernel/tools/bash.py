"""High-risk unrestricted Bash tool kept outside kernel core."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kernel.core.registry import (
    ToolExecutionContext,
    ToolRegistry,
    ToolSpec,
    ToolUserError,
)
from kernel.core.types import ToolPermission

BASH_TOOL_NAME = "bash"
_MAX_OUTPUT_BYTES = 64 * 1024


def bash_spec() -> ToolSpec:
    return ToolSpec(
        name=BASH_TOOL_NAME,
        description="Run an unrestricted Bash command in an authorized workspace.",
        args_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1, "maxLength": 16384},
                "cwd": {"type": ["string", "null"]},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 120,
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        required_permissions=frozenset(
            {ToolPermission.DESTRUCTIVE, ToolPermission.EXECUTE}
        ),
    )


def register_bash(registry: ToolRegistry) -> None:
    registry.register(bash_spec(), bash_handler)


def bash_handler(
    args: Mapping[str, Any], context: ToolExecutionContext
) -> dict[str, Any]:
    executable = context.executables.get("bash")
    if not executable:
        raise ToolUserError("bash executable is not configured for this run")
    executable_path = Path(executable).expanduser().resolve(strict=False)
    if not executable_path.is_file():
        raise ToolUserError("configured bash executable does not exist")

    cwd = _resolve_cwd(args.get("cwd"), context.workspace_roots)
    timeout = float(args.get("timeout_seconds", 30.0))
    creationflags = 0
    popen_options: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True

    process = subprocess.Popen(
        [str(executable_path), "-lc", str(args["command"])],
        cwd=str(cwd),
        env=dict(context.environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        **popen_options,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()

    stdout_value, stdout_truncated = _decode(stdout)
    stderr_value, stderr_truncated = _decode(stderr)
    return {
        "exit_code": process.returncode,
        "stdout": stdout_value,
        "stderr": stderr_value,
        "timed_out": timed_out,
        "truncated": stdout_truncated or stderr_truncated,
    }


def _resolve_cwd(value: Any, roots: tuple[Path, ...]) -> Path:
    if not roots:
        raise ToolUserError("bash requires at least one workspace root")
    if value is None:
        if len(roots) != 1:
            raise ToolUserError("cwd is required when multiple workspace roots are allowed")
        candidate = roots[0]
    elif isinstance(value, str) and value and "\x00" not in value:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            if len(roots) != 1:
                raise ToolUserError("relative cwd is ambiguous with multiple workspace roots")
            candidate = roots[0] / candidate
        candidate = candidate.resolve(strict=False)
    else:
        raise ToolUserError("cwd must be a valid path")
    if not candidate.is_dir():
        raise ToolUserError("cwd must be an existing directory")
    if not any(_within(candidate, root) for root in roots):
        raise ToolUserError("cwd must be inside an authorized workspace root")
    return candidate


def _within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath(
            (os.path.normcase(path), os.path.normcase(root))
        ) == os.path.normcase(root)
    except ValueError:
        return False


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)


def _decode(value: bytes) -> tuple[str, bool]:
    truncated = len(value) > _MAX_OUTPUT_BYTES
    return value[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"), truncated
