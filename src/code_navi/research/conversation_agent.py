"""AgentRuntime-backed decision generation for research conversations."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from code_navi.providers import ProviderSettings, create_provider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

from .conversation_schemas import (
    ResearchConversationDecision,
    ResearchConversationMessage,
    ResearchProfile,
)
from .llm import DeepSeekGuidanceProvider
from .skill_runtime import (
    RESEARCH_CLARIFICATION_SKILL_ID,
    RESEARCH_CLARIFICATION_SKILL_VERSION,
    load_research_clarification_skill,
)

research_conversation_agent = AgentSpec(
    name="research_conversation_agent",
    description="Clarifies an evolving research idea through bounded natural dialogue.",
    system_prompt=load_research_clarification_skill(),
    tool_names=(),
    output_format="json",
)


def _events_dir() -> Path:
    return Path(os.getenv("CODE_NAVI_EVENTS_DIR") or Path("var") / "runs")


@dataclass(frozen=True, slots=True)
class ConversationDecisionOutcome:
    """Validated decision result and the associated kernel audit identity."""

    status: Literal["generated", "unavailable", "failed"]
    decision: ResearchConversationDecision | None = None
    run_id: str | None = None
    event_count: int = 0
    reason: str | None = None

    @classmethod
    def generated(
        cls,
        decision: ResearchConversationDecision,
        *,
        run_id: str,
        event_count: int,
    ) -> ConversationDecisionOutcome:
        return cls("generated", decision, run_id, event_count)

    @classmethod
    def unavailable(cls) -> ConversationDecisionOutcome:
        return cls("unavailable")

    @classmethod
    def failed(cls, reason: str) -> ConversationDecisionOutcome:
        return cls("failed", reason=reason)


class RuntimeConversationDecisionGenerator:
    """Run one no-tool research decision through the public AgentRuntime."""

    def __init__(
        self,
        *,
        provider_factory: Callable[[], object] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.provider_factory = provider_factory
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        profile: ResearchProfile | Mapping[str, object],
        messages: Sequence[ResearchConversationMessage | Mapping[str, object]],
        user_message: str,
        conversation_id: str,
    ) -> ConversationDecisionOutcome:
        """Return a validated decision or a safe status for application fallback."""
        try:
            provider = self._provider()
            if provider is None:
                return ConversationDecisionOutcome.unavailable()
            request = RuntimeRequest(
                self._runtime_input(profile, messages, user_message),
                session_id=conversation_id,
                metadata={
                    "interface": "research_conversation",
                    "workflow": "clarification",
                    "skill": RESEARCH_CLARIFICATION_SKILL_ID,
                    "skill_version": RESEARCH_CLARIFICATION_SKILL_VERSION,
                },
            )
            runtime = AgentRuntime(provider, session_dir=_events_dir())
            value = runtime.run(research_conversation_agent, request)
            output_text = getattr(value, "output_text", None)
            if not isinstance(output_text, str) or not output_text.strip():
                runtime_error = getattr(value.run_result, "error", None)
                runtime_reason = getattr(value.run_result, "reason", None)
                detail = runtime_error or runtime_reason or "no provider output"
                raise ValueError(f"research conversation agent returned no JSON text: {detail}")
            decision = ResearchConversationDecision.model_validate_json(output_text)
            return ConversationDecisionOutcome.generated(
                decision,
                run_id=value.run_id,
                event_count=len(value.events),
            )
        except (TimeoutError, TypeError, ValueError) as error:
            return ConversationDecisionOutcome.failed(str(error))
        except Exception as error:
            return ConversationDecisionOutcome.failed(str(error))

    def _provider(self) -> object | None:
        if self.provider_factory is not None:
            return self.provider_factory()
        settings = ProviderSettings.resolve(timeout=self.timeout_seconds)
        if settings.name == "deepseek":
            if not os.getenv("DEEPSEEK_API_KEY"):
                return None
            return DeepSeekGuidanceProvider(timeout_seconds=self.timeout_seconds)
        if settings.name == "openai":
            if not os.getenv("OPENAI_API_KEY"):
                return None
            return create_provider(settings)
        return None

    @staticmethod
    def _runtime_input(
        profile: ResearchProfile | Mapping[str, object],
        messages: Sequence[ResearchConversationMessage | Mapping[str, object]],
        user_message: str,
    ) -> str:
        normalized_profile = (
            profile.model_dump(mode="json")
            if isinstance(profile, ResearchProfile)
            else dict(profile)
        )
        normalized_messages: list[dict[str, object]] = []
        for message in messages[-12:]:
            item = (
                message.model_dump(mode="json")
                if isinstance(message, ResearchConversationMessage)
                else dict(message)
            )
            normalized_messages.append(
                {"role": item.get("role"), "content": item.get("content")}
            )
        payload = {
            "task": "根据本轮消息更新科研画像并决定下一步对话",
            "current_profile": normalized_profile,
            "recent_messages": normalized_messages,
            "latest_user_message": user_message,
            "required_json_shape": {
                "reply": "string",
                "intent": "explore|clarify|correct|compare|summarize|prepare_search",
                "profile_patch": {
                    "topic": "string|null",
                    "motivation": "string|null",
                    "research_questions": "string[]|null",
                    "context": "string|null",
                    "methods": "string[]|null",
                    "data_requirements": "string|null",
                    "evidence_preferences": "string[]|null",
                    "time_scope": "string|null",
                    "constraints": "string[]|null",
                    "expected_output": "string|null",
                    "clear_fields": "field-name[]",
                },
                "candidate_questions": "string[]",
                "assumptions": "string[]",
                "uncertainties": "string[]",
                "next_question": "string|null",
                "suggested_answers": "string[]",
                "recommended_action": (
                    "continue_dialogue|review_profile|prepare_search"
                ),
            },
        }
        return json.dumps(payload, ensure_ascii=False)


__all__ = [
    "ConversationDecisionOutcome",
    "ResearchConversationDecision",
    "RuntimeConversationDecisionGenerator",
    "research_conversation_agent",
]
