from __future__ import annotations

import pytest

from code_navi.online_compiler.config import Settings
from code_navi.online_compiler.provider_setup import create_ai_service
from code_navi.providers import OfflineProvider, ProviderSettings


def test_settings_load_deepseek_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "DEEPSEEK")
    monkeypatch.setenv("CODE_NAVI_MODEL", "deepseek-v4-flash")

    settings = Settings.from_env()

    assert settings.ai_provider == "deepseek"
    assert settings.ai_model == "deepseek-v4-flash"


def test_settings_reject_unknown_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="CODE_NAVI_PROVIDER"):
        Settings.from_env()


def test_deepseek_service_explains_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    service = create_ai_service(
        Settings(ai_provider="deepseek", ai_model="deepseek-v4-flash")
    )

    assert service.evaluator is None
    assert service.status == "disabled"
    assert "DEEPSEEK_API_KEY" in service.message


def test_ai_service_uses_shared_provider_factory() -> None:
    captured: list[ProviderSettings] = []

    def provider_factory(settings: ProviderSettings) -> object:
        captured.append(settings)
        return OfflineProvider('{"explanation":"ok"}')

    service = create_ai_service(
        Settings(ai_provider="deepseek", ai_model="deepseek-v4-flash"),
        provider_factory=provider_factory,
    )

    assert service.evaluator is not None
    assert service.status == "ready"
    assert "deepseek-v4-flash" in service.message
    assert captured == [
        ProviderSettings(
            name="deepseek",
            model="deepseek-v4-flash",
            max_tokens=700,
            timeout=20.0,
        )
    ]


def test_mock_provider_keeps_compiler_ai_disabled() -> None:
    service = create_ai_service(Settings(ai_provider="mock", ai_model="unused"))

    assert service.evaluator is None
    assert service.status == "disabled"
