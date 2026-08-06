"""Audited, explicitly triggered model wording for research artefacts."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from code_navi.providers import ProviderConfigurationError, ProviderSettings
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

from .llm import DeepSeekGuidanceProvider

research_artifact_agent = AgentSpec(
    name="research_artifact_agent",
    description="Rewords one explicitly requested research artefact as bounded JSON.",
    system_prompt=(
        "你是科研辅助的受限表达助手。只返回 JSON，不得返回 Markdown、解释或额外字段。"
        "只能重述和组织输入中已经给出的上下文；不得访问网络、下载论文、写文件、"
        "安装依赖或运行代码；不得修改研究画像、研究计划、会话或用户确认状态。"
        "不得声称全文、实验结果、数据集、GPU、许可或资源已经可用。"
        "无法由上下文确认的内容必须标记为 to_verify，且不得新增 fact。"
    ),
    tool_names=(),
    output_format="json",
)


def _events_dir() -> Path:
    return Path(os.getenv("CODE_NAVI_EVENTS_DIR") or Path("var") / "runs")


@dataclass(frozen=True, slots=True)
class ArtifactLlmOutcome:
    """Provider result plus its Kernel audit identity."""

    status: Literal["generated", "unavailable", "failed"]
    text: str | None = None
    run_id: str | None = None
    event_count: int = 0
    reason: str | None = None

    @classmethod
    def generated(
        cls,
        text: str,
        *,
        run_id: str = "test-run",
        event_count: int = 0,
    ) -> ArtifactLlmOutcome:
        return cls("generated", text=text, run_id=run_id, event_count=event_count)

    @classmethod
    def unavailable(cls) -> ArtifactLlmOutcome:
        return cls("unavailable")

    @classmethod
    def failed(cls, reason: str) -> ArtifactLlmOutcome:
        return cls("failed", reason=reason)


class ResearchArtifactGenerator(Protocol):
    """Application boundary replaceable by deterministic tests."""

    def generate(
        self,
        *,
        kind: str,
        context: dict[str, object],
        conversation_id: str,
    ) -> ArtifactLlmOutcome: ...


class RuntimeResearchArtifactGenerator:
    """Run one explicitly requested, no-tool artefact through AgentRuntime."""

    def __init__(self, timeout_seconds: float = 8.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        kind: str,
        context: dict[str, object],
        conversation_id: str,
    ) -> ArtifactLlmOutcome:
        settings = ProviderSettings.resolve()
        if settings.name != "deepseek" or not os.getenv("DEEPSEEK_API_KEY"):
            return ArtifactLlmOutcome.unavailable()
        try:
            provider = DeepSeekGuidanceProvider(timeout_seconds=self.timeout_seconds)
            runtime = AgentRuntime(provider, session_dir=_events_dir())
            result = runtime.run(
                research_artifact_agent,
                RuntimeRequest(
                    self._runtime_input(kind, context),
                    session_id=conversation_id,
                    metadata={
                        "interface": "research_artifact",
                        "artifact_kind": kind,
                        "user_triggered": True,
                    },
                ),
            )
            if not result.output_text:
                detail = result.run_result.error or result.run_result.reason or "no output"
                raise ValueError(f"research artefact agent returned no JSON text: {detail}")
            return ArtifactLlmOutcome.generated(
                result.output_text,
                run_id=result.run_id,
                event_count=len(result.events),
            )
        except (ProviderConfigurationError, TimeoutError, ValueError) as error:
            return ArtifactLlmOutcome.failed(str(error))
        except Exception as error:
            return ArtifactLlmOutcome.failed(str(error))

    @staticmethod
    def _runtime_input(kind: str, context: Mapping[str, object]) -> str:
        payload = {
            "artifact_kind": kind,
            "validated_context": _redact_local_context(context),
        }
        return json.dumps(payload, ensure_ascii=False)


def _redact_local_context(value: object) -> object:
    """Keep local paths and accidental secret-shaped fields out of model prompts."""
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]"
            if any(token in str(key).casefold() for token in ("key", "secret", "token", "password"))
            else _redact_local_context(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_local_context(item) for item in value]
    if isinstance(value, str) and (
        "\\" in value
        or re.search(r"(?:[A-Za-z]:/|/(?:Users|home|private|tmp)/)", value)
    ):
        return "[redacted local path]"
    return value


__all__ = [
    "ArtifactLlmOutcome",
    "ResearchArtifactGenerator",
    "RuntimeResearchArtifactGenerator",
    "research_artifact_agent",
]
