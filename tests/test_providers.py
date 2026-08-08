import pytest

from code_navi.providers import (
    ProviderConfigurationError,
    ProviderSettings,
    create_provider,
)


def test_provider_settings_resolve_deepseek_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("CODE_NAVI_MODEL", "deepseek-v4-pro")

    settings = ProviderSettings.resolve()

    assert settings.name == "deepseek"
    assert settings.model == "deepseek-v4-pro"


def test_deepseek_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(ProviderConfigurationError, match="DEEPSEEK_API_KEY"):
        create_provider(ProviderSettings("deepseek", "deepseek-v4-pro"))


def test_deepseek_requires_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(ProviderConfigurationError, match="--model or CODE_NAVI_MODEL"):
        create_provider(ProviderSettings("deepseek"))


def test_deepseek_provider_is_kernel_routed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The DeepSeek provider must satisfy the kernel Provider contract."""
    pytest.importorskip("openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    provider = create_provider(
        ProviderSettings("deepseek", "deepseek-chat", temperature=0.3, max_tokens=1024)
    )

    assert callable(provider.complete)
    assert provider.capabilities.unsupported_content_blocks
    assert provider.provider_name == "deepseek"
    assert provider.temperature == 0.3
    assert provider.max_tokens == 1024


def test_unsupported_provider_is_rejected() -> None:
    with pytest.raises(ProviderConfigurationError, match="unsupported provider: anthropic"):
        create_provider(ProviderSettings("anthropic", "some-model"))


def test_openai_provider_receives_shared_output_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider = create_provider(ProviderSettings("openai", "gpt-test", max_tokens=700))

    assert provider.max_output_tokens == 700
