"""Provider status and explicit connection checks for the research UI."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from code_navi.provider_config import (
    LocalProviderConfig,
    activate_local_provider_config,
    is_plausible_api_key,
    load_local_provider_config,
    write_local_provider_config,
)
from code_navi.providers import ProviderSettings

from .conversation_agent import RuntimeConversationDecisionGenerator
from .conversation_schemas import ResearchProfile
from .llm import DEEPSEEK_DEFAULT_MODEL
from .provider_schemas import (
    ConfigureProviderRequest,
    ProviderConnectionTestResponse,
    ProviderStatusResponse,
)


class ProviderConnectionService:
    """Expose configuration state without ever returning credentials."""

    def __init__(
        self,
        decision_generator: RuntimeConversationDecisionGenerator | None = None,
    ) -> None:
        self.decision_generator = (
            decision_generator or RuntimeConversationDecisionGenerator()
        )

    def status(self) -> ProviderStatusResponse:
        """Resolve the active provider and whether required server values exist."""
        local_config = load_local_provider_config()
        settings = ProviderSettings.resolve()
        configuration_issue = None
        if settings.name == "deepseek":
            model = os.getenv("DEEPSEEK_MODEL", DEEPSEEK_DEFAULT_MODEL)
            api_key = os.getenv("DEEPSEEK_API_KEY")
            configured = is_plausible_api_key(api_key)
            if api_key and not configured:
                configuration_issue = "invalid_api_key"
        elif settings.name == "openai":
            model = settings.model
            api_key = os.getenv("OPENAI_API_KEY")
            configured = bool(model and is_plausible_api_key(api_key))
            if api_key and not is_plausible_api_key(api_key):
                configuration_issue = "invalid_api_key"
            elif api_key and not model:
                configuration_issue = "missing_model"
        else:
            model = None
            configured = False
        return ProviderStatusResponse(
            provider=settings.name,
            model=model,
            configured=configured,
            mode="model" if configured else "rules",
            configuration_method=(
                "local_file" if local_config is not None else "server_environment"
            ),
            configuration_issue=configuration_issue,
        )

    def configure(
        self,
        request: ConfigureProviderRequest,
        *,
        project_root: Path | None = None,
    ) -> ProviderStatusResponse:
        """Persist and immediately activate a validated local provider configuration."""
        model = request.model.strip() if request.model and request.model.strip() else None
        base_url = (
            request.base_url.strip()
            if request.base_url and request.base_url.strip()
            else None
        )
        config = LocalProviderConfig(
            provider=request.provider,
            api_key=request.api_key.get_secret_value().strip(),
            model=model,
            base_url=base_url,
        )
        write_local_provider_config(project_root, config)
        activate_local_provider_config(config)
        return self.status()

    def test(self) -> ProviderConnectionTestResponse:
        """Run the real structured research decision path after explicit user action."""
        status = self.status()
        if not status.configured:
            message = (
                "API Key 配置无效或不完整，请重新输入完整密钥。"
                if status.configuration_issue == "invalid_api_key"
                else "尚未配置可用的模型服务。"
            )
            return ProviderConnectionTestResponse(
                connected=False,
                provider=status.provider,
                model=status.model,
                latency_ms=0,
                message=message,
            )
        started = time.perf_counter()
        outcome = self.decision_generator.generate(
            profile=ResearchProfile(),
            messages=[],
            user_message="这是一次连接测试。请返回合法的科研澄清结构，不要调用工具。",
            conversation_id=f"provider-test-{uuid.uuid4()}",
        )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        if outcome.status == "generated":
            return ProviderConnectionTestResponse(
                connected=True,
                provider=status.provider,
                model=status.model,
                latency_ms=latency_ms,
                message="模型连接成功，结构化科研对话响应有效。",
                run_id=outcome.run_id,
            )
        failure_code, message = _safe_failure(outcome.reason)
        return ProviderConnectionTestResponse(
            connected=False,
            provider=status.provider,
            model=status.model,
            latency_ms=latency_ms,
            message=message,
            failure_code=failure_code,
        )


def _safe_failure(reason: str | None) -> tuple[str, str]:
    """Classify provider failures without exposing raw upstream responses or secrets."""
    normalized = (reason or "").casefold()
    if any(marker in normalized for marker in ("401", "authentication", "invalid api key")):
        return "invalid_credentials", "API Key 被服务商拒绝，请确认复制的是完整且有效的 Key。"
    if any(marker in normalized for marker in ("404", "model_not_found", "model not found")):
        return "model_unavailable", "模型名称不可用，请检查当前账号可访问的模型。"
    if "timed out" in normalized or "timeout" in normalized:
        return "timeout", "模型服务响应超时，请检查网络、代理或稍后重试。"
    if any(marker in normalized for marker in ("connection", "network", "dns", "name resolution")):
        return "network_error", "无法连接模型服务，请检查网络、代理和 Base URL。"
    if any(marker in normalized for marker in ("json", "validation", "no provider output")):
        return "invalid_response", "模型已响应，但没有返回科研 Agent 所需的合法结构。"
    return "provider_error", "模型服务调用失败，请检查账号余额、模型权限和服务状态。"


_provider_connection_service = ProviderConnectionService()

__all__ = ["ProviderConnectionService", "_provider_connection_service"]
