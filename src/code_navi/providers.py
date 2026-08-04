"""Provider selection for application hosts."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from kernel.core import ContentBlock, Message, ProviderResult
from kernel.core.provider import ProviderTool


class ProviderConfigurationError(ValueError):
    """Provider configuration is missing or unsupported."""


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    """Resolved provider settings with safe offline defaults."""

    name: str = "mock"
    model: str | None = None
    mock_response: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    timeout: float | None = None
    thinking: Literal["enabled", "disabled"] | None = None

    @classmethod
    def resolve(
        cls,
        *,
        name: str | None = None,
        model: str | None = None,
        mock_response: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
    ) -> ProviderSettings:
        return cls(
            (name or os.getenv("CODE_NAVI_PROVIDER") or "mock").strip().lower(),
            model or os.getenv("CODE_NAVI_MODEL"),
            mock_response,
            max_tokens,
            temperature,
            timeout,
        )


class OfflineProvider:
    """Repeatable offline provider used for CLI wiring and tests."""

    def __init__(self, response: str | None = None) -> None:
        self.response = response or (
            "当前为离线 Mock 模式：项目上下文已经装配，但没有调用真实模型。"
            "请使用 --provider openai 或 --provider deepseek 启用在线回答。"
        )
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ProviderTool] = (),
    ) -> ProviderResult:
        self.calls.append(
            {
                "messages": [message.to_json() for message in messages],
                "tools": [tool.to_json() for tool in tools],
            }
        )
        return ProviderResult(
            Message("assistant", (ContentBlock("text", {"text": self.response}),)),
            metadata={"provider": "mock"},
        )


DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


def create_provider(settings: ProviderSettings) -> object:
    """Create a kernel-compatible provider from validated application settings.

    This is the only supported way for an application module to reach a model.
    Modules must not instantiate vendor SDK clients directly, otherwise their
    runs bypass the kernel loop's Event log and permission layer.
    """
    if settings.name == "mock":
        return OfflineProvider(settings.mock_response)
    if settings.name == "openai":
        return _create_openai_provider(settings)
    if settings.name == "deepseek":
        return _create_deepseek_provider(settings)
    raise ProviderConfigurationError(f"unsupported provider: {settings.name}")


def _require_model(settings: ProviderSettings, provider_label: str) -> str:
    if not settings.model or not settings.model.strip():
        raise ProviderConfigurationError(
            f"{provider_label} provider requires --model or CODE_NAVI_MODEL"
        )
    return settings.model


def _create_openai_provider(settings: ProviderSettings) -> object:
    model = _require_model(settings, "OpenAI")
    if not os.getenv("OPENAI_API_KEY"):
        raise ProviderConfigurationError("OpenAI provider requires OPENAI_API_KEY")
    try:
        from kernel.adapters.openai import OpenAIResponsesAdapter
    except ModuleNotFoundError as exc:
        raise ProviderConfigurationError(
            'OpenAI support is not installed; run pip install -e ".[online]"'
        ) from exc
    return OpenAIResponsesAdapter(model)


def _create_deepseek_provider(settings: ProviderSettings) -> object:
    """DeepSeek speaks the OpenAI Chat Completions dialect, not Responses."""
    model = _require_model(settings, "DeepSeek")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ProviderConfigurationError("DeepSeek provider requires DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_DEFAULT_BASE_URL
    try:
        from kernel.adapters.openai_chat import OpenAIChatCompletionsAdapter
    except ModuleNotFoundError as exc:
        raise ProviderConfigurationError(
            'DeepSeek support is not installed; run pip install -e ".[online]"'
        ) from exc
    return OpenAIChatCompletionsAdapter(
        model,
        api_key=api_key,
        base_url=base_url,
        provider_name="deepseek",
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        timeout=settings.timeout,
        thinking=settings.thinking,
    )


__all__ = [
    "DEEPSEEK_DEFAULT_BASE_URL",
    "OfflineProvider",
    "ProviderConfigurationError",
    "ProviderSettings",
    "create_provider",
]
