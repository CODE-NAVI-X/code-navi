"""Application-layer construction of optional Kernel AI services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from code_navi.providers import (
    ProviderConfigurationError,
    ProviderSettings,
    create_provider,
)
from kernel.runtime import AgentRuntime

from .ai_evaluation import (
    AiEvaluator,
    AiTutor,
    KernelAiEvaluator,
    PracticeSetPlanner,
    ProblemOrganizer,
)
from .config import Settings


@dataclass(frozen=True, slots=True)
class AiService:
    evaluator: AiEvaluator | None
    tutor: AiTutor | None
    organizer: ProblemOrganizer | None
    practice_set_planner: PracticeSetPlanner | None
    status: str
    message: str


ProviderFactory = Callable[[ProviderSettings], object]


def create_ai_service(
    settings: Settings, *, provider_factory: ProviderFactory = create_provider
) -> AiService:
    if settings.ai_provider == "mock" or settings.ai_model is None:
        return AiService(
            None,
            None,
            None,
            None,
            "disabled",
            "未配置 AI 模型，规则识别与学习记录仍可使用。",
        )
    provider_settings = ProviderSettings(
        name=settings.ai_provider,
        model=settings.ai_model,
        max_tokens=settings.ai_max_output_tokens,
        timeout=settings.ai_request_timeout_seconds,
    )
    try:
        provider = provider_factory(provider_settings)
    except ProviderConfigurationError as error:
        return AiService(None, None, None, None, "disabled", str(error))
    service = KernelAiEvaluator(AgentRuntime(provider))
    label = "DeepSeek" if settings.ai_provider == "deepseek" else "OpenAI"
    return AiService(
        service,
        service,
        service,
        service,
        "ready",
        f"{label} AI 已启用（{settings.ai_model}）。",
    )
