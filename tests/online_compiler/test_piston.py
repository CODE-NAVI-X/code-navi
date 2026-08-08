from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from code_navi.online_compiler.piston import (
    ExecutionLimits,
    PistonClient,
    PistonProtocolError,
    RuntimeInfo,
    build_execute_payload,
    normalize_execution_response,
    select_python_runtime,
)


class RecordingTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, Mapping[str, Any] | None, float]] = []

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> Any:
        self.requests.append((method, url, payload, timeout_seconds))
        return self.responses.pop(0)


def test_select_python_runtime_requires_exact_pinned_version() -> None:
    runtimes = (
        RuntimeInfo("python", "3.11.0", ("py",)),
        RuntimeInfo("python", "3.12.0", ("py",)),
    )

    selected = select_python_runtime(runtimes, "3.12.0")

    assert selected.version == "3.12.0"
    with pytest.raises(PistonProtocolError, match="3.13.0"):
        select_python_runtime(runtimes, "3.13.0")


def test_execute_payload_uses_server_limits_and_fixed_main_file() -> None:
    runtime = RuntimeInfo("python", "3.12.0")
    limits = ExecutionLimits(
        wall_time_ms=2_000,
        cpu_time_ms=1_500,
        memory_bytes=128 * 1024 * 1024,
        output_bytes=64 * 1024,
    )

    payload = build_execute_payload("print(input())", "hello\n", runtime, limits)

    assert payload["files"] == [
        {"name": "main.py", "content": "print(input())", "encoding": "utf8"}
    ]
    assert payload["run_timeout"] == 2_000
    assert payload["run_cpu_time"] == 1_500
    assert payload["run_memory_limit"] == 128 * 1024 * 1024
    assert payload["args"] == []


def test_normalize_timeout_keeps_stdout_and_metrics() -> None:
    result = normalize_execution_response(
        {
            "run": {
                "stdout": "before timeout\n",
                "stderr": "",
                "code": None,
                "signal": "SIGKILL",
                "status": "TO",
                "wall_time": 2_001,
                "cpu_time": 1_998,
                "memory": 1_048_576,
            }
        },
        RuntimeInfo("python", "3.12.0"),
        ExecutionLimits(),
    )

    assert result.outcome == "time_limit"
    assert result.stdout == "before timeout\n"
    assert result.wall_time_ms == 2_001
    assert result.memory_bytes == 1_048_576


def test_client_caches_runtime_after_first_discovery() -> None:
    transport = RecordingTransport(
        [
            [{"language": "python", "version": "3.12.0", "aliases": ["py"]}],
            {
                "run": {
                    "stdout": "ok\n",
                    "stderr": "",
                    "code": 0,
                    "signal": None,
                    "status": None,
                }
            },
            {
                "run": {
                    "stdout": "again\n",
                    "stderr": "",
                    "code": 0,
                    "signal": None,
                    "status": None,
                }
            },
        ]
    )
    client = PistonClient("http://piston:2000/", transport=transport)

    result = client.execute_python(
        "print('ok')",
        "",
        version="3.12.0",
        limits=ExecutionLimits(),
    )
    second = client.execute_python(
        "print('again')",
        "",
        version="3.12.0",
        limits=ExecutionLimits(),
    )

    assert result.outcome == "success"
    assert second.stdout == "again\n"
    assert [request[1] for request in transport.requests] == [
        "http://piston:2000/api/v2/runtimes",
        "http://piston:2000/api/v2/execute",
        "http://piston:2000/api/v2/execute",
    ]
