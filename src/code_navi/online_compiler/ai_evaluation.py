"""Kernel-backed AI explanation service for deterministic compiler results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from kernel.runtime import AgentRuntime, RuntimeRequest

from .agents import code_result_explainer_agent
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


def _bounded(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[内容已截断]"
