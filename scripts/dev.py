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
        raise FileNotFoundError("npm is missing. Install Node.js 20.9 or newer.")
    if not (FRONTEND_ROOT / "node_modules").is_dir():
        raise FileNotFoundError("Frontend dependencies are missing. Run: cd frontend && npm ci")
    return command


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
                "8000",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
        ),
        subprocess.Popen(
            [npm, "run", "dev", "--", "--port", "3000"],
            cwd=FRONTEND_ROOT,
            env=environment,
        ),
    ]
    print("Code Navi backend: http://127.0.0.1:8000")
    print("Code Navi frontend: http://127.0.0.1:3000/research")
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
