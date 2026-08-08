"""Typed adapter for the subset of the Piston API used by the website."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol, cast


class PistonError(RuntimeError):
    """Base error for Piston communication and response failures."""


class PistonUnavailableError(PistonError):
    """Raised when the configured Piston service cannot be reached."""


class PistonProtocolError(PistonError):
    """Raised when Piston returns an invalid or rejected response."""


@dataclass(frozen=True)
class RuntimeInfo:
    """An installed Piston language runtime."""

    language: str
    version: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionLimits:
    """Server-owned limits for one code execution."""

    wall_time_ms: int = 2_000
    cpu_time_ms: int = 2_000
    memory_bytes: int = 134_217_728
    output_bytes: int = 65_536


@dataclass(frozen=True)
class ExecutionResult:
    """Normalized result returned to the browser."""

    outcome: str
    stdout: str
    stderr: str
    exit_code: int | None
    signal: str | None
    status: str | None
    wall_time_ms: int | None
    cpu_time_ms: int | None
    memory_bytes: int | None
    runtime: RuntimeInfo

    def as_dict(self) -> dict[str, Any]:
        """Serialize the public result without exposing raw Piston internals."""

        return {
            "outcome": self.outcome,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exitCode": self.exit_code,
            "signal": self.signal,
            "status": self.status,
            "metrics": {
                "wallTimeMs": self.wall_time_ms,
                "cpuTimeMs": self.cpu_time_ms,
                "memoryBytes": self.memory_bytes,
            },
            "runtime": {
                "language": self.runtime.language,
                "version": self.runtime.version,
            },
        }


class JsonTransport(Protocol):
    """Minimal JSON transport used to keep the adapter testable offline."""

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> Any:
        """Send one request and return its decoded JSON body."""


class UrllibJsonTransport:
    """Standard-library HTTP transport with bounded requests."""

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> Any:
        """Send JSON to Piston and translate network errors."""

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read(2_048).decode("utf-8", errors="replace")
            message = f"Piston rejected the request ({error.code}): {detail}"
            raise PistonProtocolError(message) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise PistonUnavailableError("Piston service is unavailable") from error

        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PistonProtocolError("Piston returned invalid JSON") from error


class PistonClient:
    """Access installed runtimes, package setup and Python execution."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 8.0,
        transport: JsonTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport or UrllibJsonTransport()
        self._runtime_cache: dict[str, RuntimeInfo] = {}
        self._runtime_cache_lock = Lock()

    def list_runtimes(self) -> tuple[RuntimeInfo, ...]:
        """Return all installed Piston runtimes."""

        data = self._transport.request(
            "GET", f"{self._base_url}/api/v2/runtimes", None, self._timeout_seconds
        )
        if not isinstance(data, list):
            raise PistonProtocolError("Piston runtimes response must be a list")

        runtimes: list[RuntimeInfo] = []
        for item in data:
            if not isinstance(item, dict):
                raise PistonProtocolError("Piston runtime entry must be an object")
            language = item.get("language")
            version = item.get("version")
            aliases = item.get("aliases", [])
            if not isinstance(language, str) or not isinstance(version, str):
                raise PistonProtocolError("Piston runtime is missing language or version")
            aliases_are_valid = isinstance(aliases, list) and all(
                isinstance(alias, str) for alias in aliases
            )
            if not aliases_are_valid:
                raise PistonProtocolError("Piston runtime aliases must be strings")
            runtimes.append(RuntimeInfo(language, version, tuple(aliases)))
        return tuple(runtimes)

    def list_packages(self) -> tuple[dict[str, Any], ...]:
        """Return available packages for deployment-time runtime setup."""

        data = self._transport.request(
            "GET", f"{self._base_url}/api/v2/packages", None, self._timeout_seconds
        )
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise PistonProtocolError("Piston packages response must be a list")
        return tuple(cast(dict[str, Any], item) for item in data)

    def install_package(self, language: str, version: str) -> Mapping[str, Any]:
        """Install one exact runtime package during deployment."""

        data = self._transport.request(
            "POST",
            f"{self._base_url}/api/v2/packages",
            {"language": language, "version": version},
            max(self._timeout_seconds, 300.0),
        )
        if not isinstance(data, dict):
            raise PistonProtocolError("Piston package install response must be an object")
        return cast(dict[str, Any], data)

    def execute_python(
        self,
        source: str,
        stdin: str,
        *,
        version: str,
        limits: ExecutionLimits,
    ) -> ExecutionResult:
        """Execute one Python file with server-owned resource limits."""

        runtime = self._python_runtime(version)
        payload = build_execute_payload(source, stdin, runtime, limits)
        data = self._transport.request(
            "POST", f"{self._base_url}/api/v2/execute", payload, self._timeout_seconds
        )
        if not isinstance(data, dict):
            raise PistonProtocolError("Piston execute response must be an object")
        return normalize_execution_response(cast(dict[str, Any], data), runtime, limits)

    def _python_runtime(self, version: str) -> RuntimeInfo:
        with self._runtime_cache_lock:
            runtime = self._runtime_cache.get(version)
            if runtime is None:
                runtime = select_python_runtime(self.list_runtimes(), version)
                self._runtime_cache[version] = runtime
            return runtime


def select_python_runtime(
    runtimes: tuple[RuntimeInfo, ...], requested_version: str
) -> RuntimeInfo:
    """Select the configured exact Python runtime and reject silent upgrades."""

    for runtime in runtimes:
        names = {runtime.language, *runtime.aliases}
        if "python" in names and runtime.version == requested_version:
            return runtime
    raise PistonProtocolError(f"Python {requested_version} is not installed")


def build_execute_payload(
    source: str,
    stdin: str,
    runtime: RuntimeInfo,
    limits: ExecutionLimits,
) -> dict[str, Any]:
    """Build a Piston request without accepting client-supplied commands or limits."""

    return {
        "language": runtime.language,
        "version": runtime.version,
        "files": [{"name": "main.py", "content": source, "encoding": "utf8"}],
        "stdin": stdin,
        "args": [],
        "compile_timeout": limits.wall_time_ms,
        "run_timeout": limits.wall_time_ms,
        "compile_cpu_time": limits.cpu_time_ms,
        "run_cpu_time": limits.cpu_time_ms,
        "compile_memory_limit": limits.memory_bytes,
        "run_memory_limit": limits.memory_bytes,
    }


def normalize_execution_response(
    data: Mapping[str, Any],
    runtime: RuntimeInfo,
    limits: ExecutionLimits,
) -> ExecutionResult:
    """Map Piston stage fields into the stable browser response contract."""

    compile_stage = _stage(data.get("compile"))
    run_stage = _stage(data.get("run"))
    stage = compile_stage if _stage_failed(compile_stage) else run_stage
    status = _optional_str(stage.get("status"))
    code = _optional_int(stage.get("code"))
    signal = _optional_str(stage.get("signal"))

    if compile_stage and _stage_failed(compile_stage):
        outcome = "compile_error"
    elif status == "TO":
        outcome = "time_limit"
    elif status in {"OL", "EL"}:
        outcome = "output_limit"
    elif status in {"RE", "SG", "XX"} or signal is not None or (code not in {None, 0}):
        outcome = "runtime_error" if status != "XX" else "system_error"
    else:
        outcome = "success"

    stdout = _bounded_text(stage.get("stdout"), limits.output_bytes)
    stderr = _bounded_text(stage.get("stderr"), limits.output_bytes)
    message = _optional_str(stage.get("message"))
    if message and message not in stderr:
        stderr = _bounded_text(f"{stderr}\n{message}".strip(), limits.output_bytes)

    return ExecutionResult(
        outcome=outcome,
        stdout=stdout,
        stderr=stderr,
        exit_code=code,
        signal=signal,
        status=status,
        wall_time_ms=_optional_int(stage.get("wall_time")),
        cpu_time_ms=_optional_int(stage.get("cpu_time")),
        memory_bytes=_optional_int(stage.get("memory")),
        runtime=runtime,
    )


def _stage(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PistonProtocolError("Piston execution stage must be an object")
    return cast(dict[str, Any], value)


def _stage_failed(stage: Mapping[str, Any]) -> bool:
    code = _optional_int(stage.get("code"))
    return bool(stage) and (
        code not in {None, 0}
        or _optional_str(stage.get("signal")) is not None
        or _optional_str(stage.get("status")) is not None
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _bounded_text(value: Any, max_bytes: int) -> str:
    if not isinstance(value, str):
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n[输出已截断]"
