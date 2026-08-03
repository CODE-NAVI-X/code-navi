"""Cross-platform runtime path tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_navi.paths import application_data_dir, sqlite_file_url
from code_navi.provider_config import provider_config_path


def test_default_data_paths_are_absolute_and_follow_the_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODE_NAVI_DATA_DIR", raising=False)
    monkeypatch.delenv("CODE_NAVI_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("CODE_NAVI_PROVIDER_CONFIG", raising=False)

    data_dir = application_data_dir(tmp_path)

    assert data_dir.is_absolute()
    assert data_dir == (tmp_path / ".code-navi").resolve()
    assert provider_config_path(tmp_path) == data_dir / "provider.env"


def test_data_directory_can_be_moved_without_machine_specific_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "portable-data"
    monkeypatch.setenv("CODE_NAVI_DATA_DIR", str(configured))
    monkeypatch.delenv("CODE_NAVI_PROVIDER_CONFIG", raising=False)

    assert application_data_dir() == configured.resolve()
    assert provider_config_path() == configured.resolve() / "provider.env"


def test_sqlite_url_uses_an_absolute_cross_platform_path(tmp_path: Path) -> None:
    database_path = (tmp_path / "data" / "code-navi.db").resolve()

    url = sqlite_file_url(database_path)

    assert url.startswith("sqlite:///")
    assert database_path.as_posix() in url
