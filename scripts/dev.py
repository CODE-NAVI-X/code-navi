"""Cross-platform development launcher for the backend and frontend."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def _venv_python() -> Path:
    candidate = PROJECT_ROOT / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    if not candidate.is_file():
        raise FileNotFoundError(
            "Python virtual environment is missing. Run: python -m venv .venv"
        )
    return candidate


def _npm_command() -> str:
    command = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if command is None:
        raise FileNotFoundError("npm is missing. Install Node.js 20.19 or newer.")
    if not (FRONTEND_ROOT / "node_modules").is_dir():
        raise FileNotFoundError("Frontend dependencies are missing. Run: cd frontend && npm ci")
    return command


def _port_from_environment(name: str, default: int) -> int:
    """Read one local development port without accepting an invalid value."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        port = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer port number.") from error
    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535.")
    return port


def main() -> int:
    """Start both services and stop the other one if either process exits."""
    try:
        python = _venv_python()
        npm = _npm_command()
    except FileNotFoundError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment.setdefault("CODE_NAVI_PROJECT_ROOT", str(PROJECT_ROOT))
    try:
        backend_port = _port_from_environment("CODE_NAVI_BACKEND_PORT", 8000)
        frontend_port = _port_from_environment("CODE_NAVI_FRONTEND_PORT", 3000)
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2
    processes = [
        subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                "code_navi.server:app",
                "--app-dir",
                "src",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
        ),
        subprocess.Popen(
            [npm, "run", "dev", "--", "--port", str(frontend_port)],
            cwd=FRONTEND_ROOT,
            env=environment,
        ),
    ]
    print(f"Code Navi backend: http://127.0.0.1:{backend_port}")
    print(f"Code Navi frontend: http://127.0.0.1:{frontend_port}/research")
    print("Press Ctrl+C to stop both services.")
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return next((process.returncode or 0 for process in processes if process.returncode), 0)


if __name__ == "__main__":
    raise SystemExit(main())
