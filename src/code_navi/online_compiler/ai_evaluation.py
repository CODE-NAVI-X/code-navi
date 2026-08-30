"""Kernel-backed AI explanation service for deterministic compiler results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from kernel.runtime import AgentRuntime, RuntimeRequest

from .agents import (
    code_result_explainer_agent,
    guided_code_tutor_agent,
    practice_set_planner_agent,
    problem_import_organizer_agent,
    structure_answer_reviewer_agent,
)
from .evaluation import AiFeedback, RuleAssessment, parse_ai_feedback
from .piston import ExecutionResult
from .problem_imports import ImportedProblem


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

    def evaluate_structure_answer(
        self,
        exercise: dict[str, object],
        answer: object,
        rule_results: list[dict[str, object]],
        learner_id: str | None,
    ) -> AiFeedback:
        """Return validated feedback for a static structure/framework answer."""


class AiTutor(Protocol):
    def chat(
        self,
        message: str,
        context: dict[str, object],
        history: list[dict[str, str]],
        learner_id: str | None,
    ) -> dict[str, object]:
        """Return one bounded, non-solution tutoring response."""


class ProblemOrganizer(Protocol):
    def organize(
        self, problems: list[ImportedProblem], learner_id: str | None = None
    ) -> tuple[list[ImportedProblem], list[str]]:
        """Return validated metadata suggestions and organizer warnings."""


class PracticeSetPlanner(Protocol):
    def plan_practice_set(
        self,
        request: dict[str, object],
        candidates: list[dict[str, object]],
        learner_id: str | None = None,
    ) -> dict[str, object]:
        """Return JSON practice-set ordering suggestions for known candidate IDs."""


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

    def evaluate_structure_answer(
        self,
        exercise: dict[str, object],
        answer: object,
        rule_results: list[dict[str, object]],
        learner_id: str | None,
    ) -> AiFeedback:
        """Review a static structure answer and return validated feedback."""

        prompt = json.dumps(
            {
                "exercise": exercise,
                "studentAnswer": answer,
                "ruleResults": rule_results,
                "instruction": (
                    "只做静态结构/框架评析；不得声称执行过模型或训练代码；"
                    "不得输出完整标准答案。"
                ),
            },
            ensure_ascii=False,
        )
        try:
            runtime_result = self.runtime.run(
                structure_answer_reviewer_agent,
                RuntimeRequest(
                    prompt,
                    session_id=learner_id,
                    run_id=f"structure-evaluation-{uuid4()}",
                    metadata={"mode": "structure_practice"},
                ),
            )
            if runtime_result.output_text is None:
                raise ValueError("AI response did not contain text")
            feedback = parse_ai_feedback(runtime_result.output_text)
            return _sanitize_structure_feedback(feedback)
        except Exception as exc:
            raise AiEvaluationError("AI structure feedback is temporarily unavailable") from exc

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

    def organize(
        self, problems: list[ImportedProblem], learner_id: str | None = None
    ) -> tuple[list[ImportedProblem], list[str]]:
        prompt = json.dumps(
            {
                "problems": [
                    {
                        "importId": problem.import_id,
                        "title": problem.title,
                        "description": _bounded(problem.description, 1_200),
                        "inputHint": problem.input_hint,
                        "outputHint": problem.output_hint,
                        "difficulty": problem.difficulty,
                        "tags": list(problem.tags),
                        "sampleTests": [sample.as_dict() for sample in problem.sample_tests],
                        "warnings": list(problem.warnings),
                    }
                    for problem in problems
                ],
                "instruction": (
                    "只调整已有题目的顺序、difficulty、tags、orderReason；"
                    "不要新增 importId，不要改变题意、输入输出或 sampleTests。"
                ),
            },
            ensure_ascii=False,
        )
        try:
            runtime_result = self.runtime.run(
                problem_import_organizer_agent,
                RuntimeRequest(
                    prompt,
                    session_id=learner_id,
                    run_id=f"problem-import-{uuid4()}",
                    metadata={"language": "python", "mode": "problem_import"},
                ),
            )
            if runtime_result.output_text is None:
                raise ValueError("AI organizer response did not contain text")
            return _apply_organizer_suggestions(problems, runtime_result.output_text)
        except Exception as exc:
            raise AiEvaluationError("AI problem organization is temporarily unavailable") from exc

    def plan_practice_set(
        self,
        request: dict[str, object],
        candidates: list[dict[str, object]],
        learner_id: str | None = None,
    ) -> dict[str, object]:
        prompt = json.dumps(
            {
                "request": request,
                "candidates": candidates,
                "instruction": (
                    "只能返回 candidates 中已有 id。不要新增隐藏测试；"
                    "非 built_in 来源必须说明只支持运行和 AI 评析。"
                ),
            },
            ensure_ascii=False,
        )
        try:
            runtime_result = self.runtime.run(
                practice_set_planner_agent,
                RuntimeRequest(
                    prompt,
                    session_id=learner_id,
                    run_id=f"practice-set-{uuid4()}",
                    metadata={"language": "python", "mode": "practice_set"},
                ),
            )
            if runtime_result.output_text is None:
                raise ValueError("AI practice-set planner response did not contain text")
            return _parse_json_object(runtime_result.output_text)
        except Exception as exc:
            raise AiEvaluationError("AI practice-set planning is temporarily unavailable") from exc


def _bounded(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[内容已截断]"


def _parse_tutor_reply(text: str) -> dict[str, object]:
    payload = _parse_json_object(text)
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


def _parse_json_object(text: str) -> dict[str, object]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")
    return payload


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


def _sanitize_structure_feedback(feedback: AiFeedback) -> AiFeedback:
    """Replace obvious answer leaks in structure feedback with a safe prompt."""
    if "```" in feedback.explanation or _looks_like_complete_solution(feedback.explanation):
        return AiFeedback(
            explanation=(
                "我不能直接给出完整正确顺序或可提交代码。"
                "请先说明你当前对结构顺序或关键模块的理解，我再帮你定位下一步。"
            ),
            suggestions=(
                "先解释你判断当前顺序或模块的理由。",
                "指出你觉得最不确定的一步。",
                "检查是否混淆了整体框架与局部细节。",
            ),
            quality=feedback.quality,
        )
    return feedback


def _apply_organizer_suggestions(
    problems: list[ImportedProblem], text: str
) -> tuple[list[ImportedProblem], list[str]]:
    payload = _parse_json_object(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("orderedProblems"), list):
        raise ValueError("AI organizer response must contain orderedProblems")
    known = {problem.import_id: problem for problem in problems}
    ordered: list[ImportedProblem] = []
    seen: set[str] = set()
    for suggestion in payload["orderedProblems"]:
        if not isinstance(suggestion, dict):
            continue
        import_id = suggestion.get("importId")
        if not isinstance(import_id, str) or import_id in seen or import_id not in known:
            continue
        base = known[import_id]
        tags = suggestion.get("tags")
        ordered.append(
            ImportedProblem(
                import_id=base.import_id,
                title=base.title,
                description=base.description,
                difficulty=(
                    suggestion["difficulty"]
                    if suggestion.get("difficulty") in {"easy", "medium", "hard"}
                    else base.difficulty
                ),
                tags=(
                    tuple(tag.strip() for tag in tags if isinstance(tag, str) and tag.strip())[:6]
                    if isinstance(tags, list) and tags
                    else base.tags
                ),
                input_hint=base.input_hint,
                output_hint=base.output_hint,
                starter_code=base.starter_code,
                sample_tests=base.sample_tests,
                confidence=base.confidence,
                warnings=base.warnings,
                order_reason=(
                    suggestion["orderReason"].strip()
                    if isinstance(suggestion.get("orderReason"), str)
                    and suggestion["orderReason"].strip()
                    else base.order_reason
                ),
            )
        )
        seen.add(import_id)
    ordered.extend(problem for problem in problems if problem.import_id not in seen)
    warnings = payload.get("warnings")
    return ordered, (
        [warning for warning in warnings if isinstance(warning, str)][:6]
        if isinstance(warnings, list)
        else []
    )
