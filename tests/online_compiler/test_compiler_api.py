from __future__ import annotations

from fastapi.testclient import TestClient

from code_navi.online_compiler.application import CompilerApplication
from code_navi.online_compiler.config import Settings
from code_navi.online_compiler.piston import ExecutionLimits, ExecutionResult, RuntimeInfo
from code_navi.online_compiler.router import get_compiler_application
from code_navi.server import app


class FakePistonGateway:
    def __init__(self) -> None:
        self.runtime = RuntimeInfo("python", "3.12.0", ("py",))
        self.calls: list[tuple[str, str, str, ExecutionLimits]] = []

    def list_runtimes(self) -> tuple[RuntimeInfo, ...]:
        return (self.runtime,)

    def execute_python(
        self,
        source: str,
        stdin: str,
        *,
        version: str,
        limits: ExecutionLimits,
    ) -> ExecutionResult:
        self.calls.append((source, stdin, version, limits))
        return ExecutionResult(
            outcome="success",
            stdout="hello\n",
            stderr="",
            exit_code=0,
            signal=None,
            status=None,
            wall_time_ms=12,
            cpu_time_ms=8,
            memory_bytes=1_024,
            runtime=self.runtime,
        )


def test_compiler_api_execute_uses_main_fastapi_router() -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            runtime = client.get("/api/v1/compiler/runtime")
            executed = client.post(
                "/api/v1/compiler/execute",
                json={"language": "python", "source": "print('hello')"},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert runtime.status_code == 200
    assert runtime.json()["ready"] is True
    assert executed.status_code == 200
    assert executed.json()["outcome"] == "success"
    assert gateway.calls[0][0] == "print('hello')"


def test_compiler_api_rejects_invalid_payload_without_gateway_call() -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/compiler/execute",
                json={"language": "javascript", "source": "console.log(1)"},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 400
    assert "Python" in response.json()["error"]
    assert gateway.calls == []


def test_compiler_api_analyzes_uploaded_problem_text() -> None:
    compiler = CompilerApplication(FakePistonGateway(), Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/compiler/problem-imports/analyze",
                json={
                    "text": (
                        "题目：字符串回文判断\n"
                        "描述：判断字符串是否为回文。\n"
                        "输入：一行字符串\n"
                        "输出：YES 或 NO"
                    )
                },
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "deterministic_rule"
    assert payload["problems"][0]["title"] == "字符串回文判断"
    assert "字符串" in payload["problems"][0]["tags"]


def test_compiler_api_generates_practice_set() -> None:
    compiler = CompilerApplication(FakePistonGateway(), Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/compiler/problem-sets/generate",
                json={"prompt": "练习循环和列表", "targetCount": 2},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "deterministic_rule"
    assert len(payload["orderedProblems"]) == 2
    assert payload["orderedProblems"][0]["source"] == "built_in"
