"""Environment-backed configuration for the compiler website."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime settings controlled by the application host."""

    host: str = "0.0.0.0"
    port: int = 8080
    piston_base_url: str = "http://127.0.0.1:2000"
    python_version: str = "3.12.0"
    request_timeout_seconds: float = 8.0
    max_source_bytes: int = 65_536
    max_stdin_bytes: int = 65_536
    run_timeout_ms: int = 2_000
    run_cpu_time_ms: int = 2_000
    run_memory_limit_bytes: int = 134_217_728
    output_limit_bytes: int = 65_536
    database_path: str = "var/learning-records.sqlite3"
    ai_provider: str = "openai"
    ai_model: str | None = None
    ai_max_output_tokens: int = 700
    ai_request_timeout_seconds: float = 20.0
    deepseek_base_url: str = "https://api.deepseek.com"

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables with safe local defaults."""

        return cls(
            host=os.getenv("COMPILER_HOST", "0.0.0.0"),
            port=_positive_int("COMPILER_PORT", 8080),
            piston_base_url=os.getenv("PISTON_BASE_URL", "http://127.0.0.1:2000").rstrip("/"),
            python_version=os.getenv("PISTON_PYTHON_VERSION", "3.12.0"),
            request_timeout_seconds=_positive_float("PISTON_REQUEST_TIMEOUT_SECONDS", 8.0),
            max_source_bytes=_positive_int("COMPILER_MAX_SOURCE_BYTES", 65_536),
            max_stdin_bytes=_positive_int("COMPILER_MAX_STDIN_BYTES", 65_536),
            run_timeout_ms=_positive_int("COMPILER_RUN_TIMEOUT_MS", 2_000),
            run_cpu_time_ms=_positive_int("COMPILER_RUN_CPU_TIME_MS", 2_000),
            run_memory_limit_bytes=_positive_int(
                "COMPILER_RUN_MEMORY_LIMIT_BYTES", 134_217_728
            ),
            output_limit_bytes=_positive_int("COMPILER_OUTPUT_LIMIT_BYTES", 65_536),
            database_path=os.getenv(
                "COMPILER_DATABASE_PATH", "var/learning-records.sqlite3"
            ),
            ai_provider=_choice(
                "COMPILER_AI_PROVIDER", "openai", frozenset({"openai", "deepseek"})
            ),
            ai_model=_optional_string("COMPILER_AI_MODEL"),
            ai_max_output_tokens=_positive_int("COMPILER_AI_MAX_OUTPUT_TOKENS", 700),
            ai_request_timeout_seconds=_positive_float(
                "COMPILER_AI_REQUEST_TIMEOUT_SECONDS", 20.0
            ),
            deepseek_base_url=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
        )


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _optional_string(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _choice(name: str, default: str, allowed: frozenset[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {options}")
    return value
