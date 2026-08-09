from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev.py"
_SPEC = importlib.util.spec_from_file_location("code_navi_dev_launcher", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
launcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(launcher)


def test_backend_port_uses_default_or_valid_local_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODE_NAVI_BACKEND_PORT", raising=False)
    assert launcher._port_from_environment("CODE_NAVI_BACKEND_PORT", 8000) == 8000

    monkeypatch.setenv("CODE_NAVI_BACKEND_PORT", "8001")
    assert launcher._port_from_environment("CODE_NAVI_BACKEND_PORT", 8000) == 8001
