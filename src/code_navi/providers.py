"""Provider selection for application hosts."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

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

    @classmethod
    def resolve(
        cls,
        *,
        name: str | None = None,
        model: str | None = None,
        mock_response: str | None = None,
    ) -> ProviderSettings:
        return cls(
            (name or os.getenv("CODE_NAVI_PROVIDER") or "mock").strip().lower(),
            model or os.getenv("CODE_NAVI_MODEL"),
            mock_response,
        )


class OfflineProvider:
    """Repeatable offline provider used for CLI wiring and tests."""

    def __init__(self, response: str | None = None) -> None:
        self.response = response or (
            "当前为离线 Mock 模式：项目上下文已经装配，但没有调用真实模型。"
            "请使用 --provider openai --model <模型名> 启用在线回答。"
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


def create_provider(settings: ProviderSettings) -> object:
    """Create a kernel-compatible provider from validated application settings."""
    if settings.name == "mock":
        return OfflineProvider(settings.mock_response)
    if settings.name != "openai":
        raise ProviderConfigurationError(f"unsupported provider: {settings.name}")
    if not settings.model or not settings.model.strip():
        raise ProviderConfigurationError(
            "OpenAI provider requires --model or CODE_NAVI_MODEL"
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise ProviderConfigurationError("OpenAI provider requires OPENAI_API_KEY")
    try:
        from kernel.adapters.openai import OpenAIResponsesAdapter
    except ModuleNotFoundError as exc:
        raise ProviderConfigurationError(
            'OpenAI support is not installed; run pip install -e ".[online]"'
        ) from exc
    return OpenAIResponsesAdapter(settings.model)


__all__ = [
    "OfflineProvider",
    "ProviderConfigurationError",
    "ProviderSettings",
    "create_provider",
]
