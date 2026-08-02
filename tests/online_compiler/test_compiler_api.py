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

