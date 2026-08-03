"""Offline tests for local provider configuration and connection visibility."""

from __future__ import annotations

from collections.abc import Generator
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from code_navi.cli import main
from code_navi.research.conversation_agent import ConversationDecisionOutcome
from code_navi.research.provider_service import _provider_connection_service
from code_navi.server import app


@pytest.fixture(autouse=True)
def clean_provider_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER_CONFIG", str(tmp_path / "provider.env"))
    for name in (
        "CODE_NAVI_PROVIDER",
        "CODE_NAVI_MODEL",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def restore_connection_generator() -> Generator[None, None, None]:
    original = _provider_connection_service.decision_generator
    yield
    _provider_connection_service.decision_generator = original


def test_provider_status_distinguishes_rules_from_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        offline = client.get("/api/v1/research/provider/status")
        monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-test-value")
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")
        configured = client.get("/api/v1/research/provider/status")

    assert offline.status_code == 200
    assert offline.json()["mode"] == "rules"
    assert offline.json()["configured"] is False
    assert configured.status_code == 200
    assert configured.json()["mode"] == "model"
    assert configured.json()["model"] == "deepseek-test"
    assert configured.json()["configuration_method"] == "server_environment"
    assert "secret-test-value" not in configured.text


def test_provider_status_rejects_truncated_key_without_calling_it_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "xx")

    with TestClient(app) as client:
        status_response = client.get("/api/v1/research/provider/status")
        test_response = client.post("/api/v1/research/provider/test")

    assert status_response.status_code == 200
    assert status_response.json()["configured"] is False
    assert status_response.json()["configuration_issue"] == "invalid_api_key"
    assert test_response.json()["connected"] is False
    assert "不完整" in test_response.json()["message"]


class FakeConnectionGenerator:
    def __init__(self, outcome: ConversationDecisionOutcome) -> None:
        self.outcome = outcome
        self.calls = 0

    def generate(self, **_kwargs: object) -> ConversationDecisionOutcome:
        self.calls += 1
        return self.outcome


def test_connection_test_returns_audit_id_without_leaking_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-test-value")
    fake = FakeConnectionGenerator(
        ConversationDecisionOutcome.failed(
            "401 authentication failed for secret-test-value"
        )
    )
    _provider_connection_service.decision_generator = fake

    with TestClient(app) as client:
        response = client.post("/api/v1/research/provider/test")

    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert response.json()["failure_code"] == "invalid_credentials"
    assert response.json()["run_id"] is None
    assert "secret-test-value" not in response.text
    assert fake.calls == 1


def test_local_ui_can_save_and_immediately_activate_provider_without_echoing_key(
    tmp_path: Path,
) -> None:
    secret = "secret-browser-test-value"

    with TestClient(app) as client:
        response = client.put(
            "/api/v1/research/provider/configuration",
            json={
                "provider": "deepseek",
                "api_key": secret,
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
            },
        )
        refreshed = client.get("/api/v1/research/provider/status")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["configuration_method"] == "local_file"
    assert refreshed.json()["model"] == "deepseek-v4-flash"
    assert secret not in response.text
    assert secret not in refreshed.text
    config_text = (tmp_path / "provider.env").read_text(encoding="utf-8")
    assert f'DEEPSEEK_API_KEY="{secret}"' in config_text


def test_ui_configuration_rejects_incomplete_keys_without_writing_file(
    tmp_path: Path,
) -> None:
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/research/provider/configuration",
            json={
                "provider": "deepseek",
                "api_key": "too-short",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
            },
        )

    assert response.status_code == 422
    assert "too-short" not in response.text
    assert not (tmp_path / "provider.env").exists()


def test_browser_configuration_can_be_disabled_for_nonlocal_deployments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_ALLOW_BROWSER_PROVIDER_CONFIG", "false")

    with TestClient(app) as client:
        response = client.put(
            "/api/v1/research/provider/configuration",
            json={
                "provider": "deepseek",
                "api_key": "secret-browser-test-value",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
            },
        )

    assert response.status_code == 403
    assert "已禁用" in response.json()["detail"]


def test_configure_provider_writes_ignored_local_file_without_echoing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODE_NAVI_PROVIDER_CONFIG", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)
    monkeypatch.setattr("code_navi.cli.getpass", lambda _prompt: "secret-test-value")

    exit_code = main(
        [
            "configure-provider",
            "--project",
            str(project),
            "--provider",
            "deepseek",
            "--model",
            "deepseek-test",
        ]
    )

    config_path = project / ".code-navi" / "provider.env"
    assert exit_code == 0
    assert config_path.exists()
    assert "DEEPSEEK_API_KEY=\"secret-test-value\"" in config_path.read_text(
        encoding="utf-8"
    )
    assert "secret-test-value" not in stdout.getvalue()
    assert "secret-test-value" not in stderr.getvalue()
    assert "已读取 17 个字符" in stdout.getvalue()


def test_configure_provider_retries_an_incomplete_hidden_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODE_NAVI_PROVIDER_CONFIG", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    answers = iter(("xx", "secret-test-value"))
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)
    monkeypatch.setattr("code_navi.cli.getpass", lambda _prompt: next(answers))

    exit_code = main(
        [
            "configure-provider",
            "--project",
            str(project),
            "--provider",
            "deepseek",
            "--model",
            "deepseek-test",
        ]
    )

    assert exit_code == 0
    assert "只读取到 2 个字符" in stderr.getvalue()
    assert "已读取 17 个字符" in stdout.getvalue()
    assert "xx" not in (project / ".code-navi" / "provider.env").read_text(
        encoding="utf-8"
    )
