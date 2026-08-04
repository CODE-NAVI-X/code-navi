"""Bounded DeepSeek wording for research artefacts owned by application rules."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Thread
from typing import Literal, Protocol

from code_navi.providers import ProviderConfigurationError, ProviderSettings
from kernel.core import ContentBlock, Message

from .llm import DeepSeekGuidanceProvider


@dataclass(frozen=True, slots=True)
class ArtifactLlmOutcome:
    """Provider result expressed without leaking provider errors into responses."""

    status: Literal["generated", "unavailable", "failed"]
    text: str | None = None
    reason: str | None = None

    @classmethod
    def generated(cls, text: str) -> ArtifactLlmOutcome:
        return cls("generated", text=text)

    @classmethod
    def unavailable(cls) -> ArtifactLlmOutcome:
        return cls("unavailable")

    @classmethod
    def failed(cls, reason: str) -> ArtifactLlmOutcome:
        return cls("failed", reason=reason)


class ResearchArtifactGenerator(Protocol):
    """Application boundary that can be replaced by a deterministic fake in tests."""

    def generate(
        self, *, kind: str, context: dict[str, object]
    ) -> ArtifactLlmOutcome: ...


class DeepSeekResearchArtifactGenerator:
    """Use the existing DeepSeek settings for wording only; it never exposes tools."""

    def __init__(self, timeout_seconds: float = 8.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def generate(
        self, *, kind: str, context: dict[str, object]
    ) -> ArtifactLlmOutcome:
        settings = ProviderSettings.resolve()
        if settings.name != "deepseek" or not os.getenv("DEEPSEEK_API_KEY"):
            return ArtifactLlmOutcome.unavailable()
        try:
            response = self._complete(DeepSeekGuidanceProvider(), self._message(kind, context))
            return ArtifactLlmOutcome.generated(self._text(response.message))
        except (ProviderConfigurationError, TimeoutError, ValueError) as error:
            return ArtifactLlmOutcome.failed(str(error))
        except Exception as error:  # Network/SDK failures must preserve offline rules.
            return ArtifactLlmOutcome.failed(str(error))

    def _complete(self, provider: object, message: Message) -> object:
        results: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def complete() -> None:
            try:
                results.put((True, provider.complete((message,))))  # type: ignore[attr-defined]
            except Exception as error:
                results.put((False, error))

        Thread(target=complete, daemon=True).start()
        try:
            succeeded, value = results.get(timeout=self.timeout_seconds)
        except Empty as error:
            raise TimeoutError("research artefact provider timed out") from error
        if succeeded:
            return value
        if isinstance(value, Exception):
            raise value
        raise RuntimeError("research artefact provider failed without an exception")

    @staticmethod
    def _text(message: Message) -> str:
        for block in message.content:
            if block.type == "text" and isinstance(block.data.get("text"), str):
                return block.data["text"]
        raise ValueError("research artefact provider returned no text")

    @staticmethod
    def _message(kind: str, context: Mapping[str, object]) -> Message:
        prompt = {
            "role": "科研辅助的受限表达助手",
            "artifact_kind": kind,
            "hard_rules": [
                "只返回 JSON，不得返回 Markdown、解释或额外字段。",
                "只能重述和组织给定上下文；不能访问网络、下载论文、写文件、安装依赖或运行代码。",
                "不得修改研究画像、研究计划、会话状态或用户确认状态。",
                "不得声称论文全文、实验结果、数据集、GPU、许可或资源已可用。",
                "若无法由上下文直接确认，classification 必须为 to_verify。",
                "模型生成的难点项不得使用 fact；事实由规则层和已保存来源负责。",
            ],
            "validated_context": _redact_local_context(context),
        }
        return Message(
            "user", (ContentBlock("text", {"text": json.dumps(prompt, ensure_ascii=False)}),)
        )


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
    "DeepSeekResearchArtifactGenerator",
    "ResearchArtifactGenerator",
]
