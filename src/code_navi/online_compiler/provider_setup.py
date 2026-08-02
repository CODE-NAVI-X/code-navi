"""Application-layer construction of the optional Kernel AI runtime."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from kernel.adapters.openai import OpenAIResponsesAdapter
from kernel.runtime import AgentRuntime

from .ai_evaluation import AiEvaluator, KernelAiEvaluator
from .config import Settings
from .deepseek import DeepSeekChatCompletionsAdapter


@dataclass(frozen=True, slots=True)
class AiService:
    """Configured evaluator plus a browser-safe availability description."""

    evaluator: AiEvaluator | None
    status: str
    message: str


ClientFactory = Callable[..., Any]


def create_ai_service(
    settings: Settings,
    *,
    client_factory: ClientFactory | None = None,
) -> AiService:
    """Create a stateless Kernel runtime only when model and credential exist."""

    if settings.ai_model is None:
        return AiService(None, "disabled", "未配置 AI 模型，规则识别与学习记录仍可使用。")
    if settings.ai_provider == "deepseek":
        return _create_deepseek_service(settings, client_factory or OpenAI)
    return _create_openai_service(settings, client_factory or OpenAI)


def _create_deepseek_service(
    settings: Settings,
    client_factory: ClientFactory,
) -> AiService:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return AiService(None, "disabled", "已选择 DeepSeek，但尚未配置 DEEPSEEK_API_KEY。")
    client = client_factory(
        api_key=api_key,
        base_url=settings.deepseek_base_url,
        timeout=settings.ai_request_timeout_seconds,
        max_retries=0,
    )
    provider = DeepSeekChatCompletionsAdapter(
        settings.ai_model or "",
        client=client,
        max_output_tokens=settings.ai_max_output_tokens,
    )
    return AiService(
        KernelAiEvaluator(AgentRuntime(provider)),
        "ready",
        f"DeepSeek AI 评析已启用（{settings.ai_model}）。",
    )


def _create_openai_service(
    settings: Settings,
    client_factory: ClientFactory,
) -> AiService:
    if not os.getenv("OPENAI_API_KEY"):
        return AiService(None, "disabled", "已选择 OpenAI，但尚未配置 OPENAI_API_KEY。")
    client = client_factory(timeout=settings.ai_request_timeout_seconds, max_retries=0)
    provider = OpenAIResponsesAdapter(
        settings.ai_model or "",
        client=client,
        max_output_tokens=settings.ai_max_output_tokens,
    )
    return AiService(
        KernelAiEvaluator(AgentRuntime(provider)),
        "ready",
        f"OpenAI AI 评析已启用（{settings.ai_model}）。",
    )
