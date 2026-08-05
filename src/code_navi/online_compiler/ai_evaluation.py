"""Kernel-backed AI explanation service for deterministic compiler results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from kernel.runtime import AgentRuntime, RuntimeRequest

from .agents import code_result_explainer_agent, guided_code_tutor_agent
from .evaluation import AiFeedback, RuleAssessment, parse_ai_feedback
from .piston import ExecutionResult


class AiEvaluationError(RuntimeError):
    """Raised when the configured model cannot produce validated feedback."""


class AiEvaluator(Protocol):
    """Application-facing capability for optional AI feedback."""

    def evaluate(
        self,
        source: str,
        result: ExecutionResult,
        assessment: RuleAssessment,
        learner_id: str | None,
    ) -> AiFeedback:
        """Return validated feedback without changing the rule assessment."""


class AiTutor(Protocol):
    def chat(
        self,
        message: str,
        context: dict[str, object],
        history: list[dict[str, str]],
        learner_id: str | None,
    ) -> dict[str, object]:
        """Return one bounded, non-solution tutoring response."""


@dataclass(frozen=True, slots=True)
class KernelAiEvaluator:
    """Run the result explainer through the Kernel public runtime interface."""

    runtime: AgentRuntime

    def evaluate(
        self,
        source: str,
        result: ExecutionResult,
        assessment: RuleAssessment,
        learner_id: str | None,
    ) -> AiFeedback:
        """Execute one stateless AgentRuntime request and validate its JSON."""

        prompt = json.dumps(
            {
                "language": "python",
                "source": _bounded(source, 20_000),
                "ruleAssessment": assessment.as_dict(),
                "execution": {
                    "outcome": result.outcome,
                    "stderr": _bounded(result.stderr, 8_000),
                    "stdout": _bounded(result.stdout, 8_000),
                    "exitCode": result.exit_code,
                    "wallTimeMs": result.wall_time_ms,
                    "memoryBytes": result.memory_bytes,
                },
            },
            ensure_ascii=False,
        )
        try:
            runtime_result = self.runtime.run(
                code_result_explainer_agent,
                RuntimeRequest(
                    prompt,
                    session_id=learner_id,
                    run_id=f"evaluation-{uuid4()}",
                    metadata={"rule_category": assessment.category, "language": "python"},
                ),
            )
            if runtime_result.output_text is None:
                raise ValueError("AI response did not contain text")
            return parse_ai_feedback(runtime_result.output_text)
        except Exception as exc:
            raise AiEvaluationError("AI feedback is temporarily unavailable") from exc

    def chat(
        self,
        message: str,
        context: dict[str, object],
        history: list[dict[str, str]],
        learner_id: str | None,
    ) -> dict[str, object]:
        prompt = json.dumps(
            {
                "studentQuestion": _bounded(message, 800),
                "exerciseContext": context,
                "recentDialogue": history[-8:],
                "instruction": "只给最小引导，不给完整答案，不输出可直接提交的代码。",
            },
            ensure_ascii=False,
        )
        try:
            runtime_result = self.runtime.run(
                guided_code_tutor_agent,
                RuntimeRequest(
                    prompt,
                    session_id=learner_id,
                    run_id=f"tutor-{uuid4()}",
                    metadata={"language": "python", "mode": "guided_tutor"},
                ),
            )
            if runtime_result.output_text is None:
                raise ValueError("AI tutor response did not contain text")
            return _parse_tutor_reply(runtime_result.output_text)
        except Exception as exc:
            raise AiEvaluationError("AI tutor is temporarily unavailable") from exc


def _bounded(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[内容已截断]"


def _parse_tutor_reply(text: str) -> dict[str, object]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise ValueError("AI tutor response must be an object")
    reply = payload.get("reply")
    strategy = payload.get("strategy")
    blocked = payload.get("blocked")
    if not isinstance(reply, str) or not reply.strip() or len(reply) > 1_500:
        raise ValueError("AI tutor reply is invalid")
    if strategy not in {"question", "hint", "explanation"} or not isinstance(blocked, bool):
        raise ValueError("AI tutor response fields are invalid")
    if _looks_like_complete_solution(reply):
        return {
            "reply": "我不能直接给出可提交的完整实现。先指出一个最小步骤：你准备如何表示当前状态？",
            "strategy": "question",
            "blocked": True,
        }
    return {"reply": reply.strip(), "strategy": strategy, "blocked": blocked}


def _looks_like_complete_solution(reply: str) -> bool:
    if "```" in reply:
        return True
    code_like = 0
    for line in reply.splitlines():
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "for ", "while ", "if ", "print(")):
            code_like += 1
        elif " = " in stripped and not stripped.startswith(("例如", "假设")):
            code_like += 1
    return code_like >= 3
