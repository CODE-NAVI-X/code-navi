"""Release checks for machine-independent development entry points."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_uses_its_own_directory_and_loopback_host() -> None:
    source = (ROOT / "dev-start.cmd").read_text(encoding="utf-8")

    assert 'set "PROJECT_DIR=%~dp0"' in source
    assert '%CD%' not in source
    assert "--host 127.0.0.1" in source


def test_cross_platform_launcher_resolves_root_from_its_file() -> None:
    source = (ROOT / "scripts" / "dev.py").read_text(encoding="utf-8")

    assert "Path(__file__).resolve().parents[1]" in source
    assert 'environment.setdefault("CODE_NAVI_PROJECT_ROOT"' in source
    assert "Scripts/python.exe" in source
    assert "bin/python" in source


def test_frontend_api_example_is_trackable_and_contains_no_secret() -> None:
    source = (ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")

    assert "NEXT_PUBLIC_CODE_NAVI_API_URL=" in source
    assert "API_KEY" not in source
