from __future__ import annotations

import pytest

from code_navi.online_compiler.config import Settings
from code_navi.online_compiler.provider_setup import create_ai_service


class FakeOpenAIClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def test_settings_load_deepseek_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPILER_AI_PROVIDER", "DEEPSEEK")
    monkeypatch.setenv("COMPILER_AI_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")

    settings = Settings.from_env()

    assert settings.ai_provider == "deepseek"
    assert settings.ai_model == "deepseek-v4-flash"
    assert settings.deepseek_base_url == "https://api.deepseek.com"


def test_settings_reject_unknown_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPILER_AI_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="COMPILER_AI_PROVIDER"):
        Settings.from_env()


def test_deepseek_service_explains_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    service = create_ai_service(
        Settings(ai_provider="deepseek", ai_model="deepseek-v4-flash"),
        client_factory=FakeOpenAIClient,
    )

    assert service.evaluator is None
    assert service.status == "disabled"
    assert "DEEPSEEK_API_KEY" in service.message


def test_deepseek_service_is_ready_with_local_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    service = create_ai_service(
        Settings(ai_provider="deepseek", ai_model="deepseek-v4-flash"),
        client_factory=FakeOpenAIClient,
    )

    assert service.evaluator is not None
    assert service.status == "ready"
    assert "deepseek-v4-flash" in service.message
