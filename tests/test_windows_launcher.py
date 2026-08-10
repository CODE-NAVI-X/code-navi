"""Contract checks for the documented one-click Windows launcher."""

from pathlib import Path


def test_windows_launcher_prepares_then_starts_both_services() -> None:
    launcher = Path(__file__).resolve().parents[1] / "启动科研助手.bat"

    assert launcher.is_file()
    content = launcher.read_text(encoding="utf-8-sig")
    assert 'cd /d "%~dp0"' in content
    assert 'set "CODE_NAVI_DATABASE_URL=sqlite:///./.code-navi/local_demo.db"' in content
    assert '".venv\\Scripts\\python.exe" -m alembic upgrade head' in content
    assert '".venv\\Scripts\\python.exe" scripts\\dev.py' in content
    assert "frontend\\node_modules" in content
    assert "pip install -e" in content
    assert "Port 3000 or 8000 is already in use" in content
    assert "pause\ngoto :end\n\n:port_in_use" in content
