"""Application rules between the browser API and Piston adapter."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from threading import Lock
from time import monotonic, perf_counter
from typing import Any, Protocol
from uuid import UUID, uuid4

from .ai_evaluation import AiEvaluationError, AiEvaluator
from .config import Settings
from .evaluation import AiFeedback, RuleAssessment, classify_execution
from .learning_records import LearningRecordStore
from .piston import ExecutionLimits, ExecutionResult, PistonError, RuntimeInfo


class ValidationError(ValueError):
    """Raised when a browser execution request violates the public contract."""


class PistonGateway(Protocol):
    """Execution capabilities required by the web application."""

    def list_runtimes(self) -> tuple[RuntimeInfo, ...]:
        """Return installed runtimes."""

    def execute_python(
        self,
        source: str,
        stdin: str,
        *,
        version: str,
        limits: ExecutionLimits,
    ) -> ExecutionResult:
        """Execute Python source once."""


@dataclass(frozen=True)
class ApiResponse:
    """HTTP-independent API result used by the request handler and tests."""

    status_code: int
    body: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PendingEvaluation:
    """Server-owned execution context referenced by an opaque browser ticket."""

    source: str
    result: ExecutionResult
    assessment: RuleAssessment
    learner_id: str | None
    record_id: str | None
    created_at: float


PENDING_EVALUATION_TTL_SECONDS = 300.0
MAX_PENDING_EVALUATIONS = 256


class CompilerApplication:
    """Validate public requests and expose stable compiler responses."""

    def __init__(
        self,
        gateway: PistonGateway,
        settings: Settings,
        *,
        evaluator: AiEvaluator | None = None,
        ai_status: str = "disabled",
        ai_message: str = "未配置 AI 模型，规则识别仍可使用。",
        record_store: LearningRecordStore | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings
        self._evaluator = evaluator
        self._ai_status = ai_status
        self._ai_message = ai_message
        self._record_store = record_store
        self._pending_evaluations: dict[str, PendingEvaluation] = {}
        self._pending_lock = Lock()
        self._limits = ExecutionLimits(
            wall_time_ms=settings.run_timeout_ms,
            cpu_time_ms=settings.run_cpu_time_ms,
            memory_bytes=settings.run_memory_limit_bytes,
            output_bytes=settings.output_limit_bytes,
        )

    def runtime_status(self) -> ApiResponse:
        """Report whether the pinned Python runtime is installed."""

        try:
            runtimes = self._gateway.list_runtimes()
        except PistonError:
            return ApiResponse(
                503,
                {
                    "ready": False,
                    "message": "执行服务暂时不可用，请稍后重试。",
                },
            )

        ready = any(
            runtime.version == self._settings.python_version
            and "python" in {runtime.language, *runtime.aliases}
            for runtime in runtimes
        )
        return ApiResponse(
            200 if ready else 503,
            {
                "ready": ready,
                "language": "Python",
                "version": self._settings.python_version,
                "limits": {
                    "wallTimeMs": self._limits.wall_time_ms,
                    "memoryBytes": self._limits.memory_bytes,
                    "sourceBytes": self._settings.max_source_bytes,
                },
                "message": "运行环境已就绪" if ready else "Python 运行时尚未安装",
                "ai": {
                    "status": self._ai_status,
                    "message": self._ai_message,
                },
            },
        )

    def execute(self, payload: Any) -> ApiResponse:
        """Validate a browser request, execute Python and normalize failures."""

        try:
            source, stdin, learner_id, ai_enabled = self._validate_payload(payload)
        except ValidationError as error:
            return ApiResponse(400, {"error": str(error)})

        execution_started = perf_counter()
        try:
            result = self._gateway.execute_python(
                source,
                stdin,
                version=self._settings.python_version,
                limits=self._limits,
            )
        except PistonError:
            return ApiResponse(
                503,
                {
                    "error": "执行服务暂时不可用，请确认 Piston 与 Python 运行时已经启动。"
                },
            )
        execution_round_trip_ms = round((perf_counter() - execution_started) * 1_000)

        assessment = classify_execution(result)
        should_defer_ai = (
            ai_enabled
            and self._evaluator is not None
            and assessment.category != "system_error"
        )
        if not ai_enabled:
            feedback = None
            ai_body: dict[str, Any] = {
                "status": "disabled",
                "message": "本次运行未开启 AI 评析。",
            }
        elif should_defer_ai:
            feedback = None
            ai_body = {
                "status": "pending",
                "message": "代码运行完成，AI 正在评析。",
            }
        else:
            feedback, ai_body = self._evaluate(source, result, assessment, learner_id)
        record_body: dict[str, Any] | None = None
        record_id: str | None = None
        if learner_id is not None and self._record_store is not None:
            try:
                record = self._record_store.add(
                    learner_id,
                    source,
                    result,
                    assessment,
                    ai_status=ai_body["status"],
                    feedback=feedback,
                )
                record_id = record.record_id
                record_body = record.as_dict()
            except (OSError, ValueError, sqlite3.Error):
                record_body = {"status": "unavailable"}

        if should_defer_ai:
            ai_body["evaluationId"] = self._queue_evaluation(
                source,
                result,
                assessment,
                learner_id,
                record_id,
            )

        body = result.as_dict()
        body.update(
            {
                "assessment": assessment.as_dict(),
                "ai": ai_body,
                "record": record_body,
                "serviceTiming": {"executionRoundTripMs": execution_round_trip_ms},
            }
        )
        return ApiResponse(200, body)

    def evaluate(self, payload: Any) -> ApiResponse:
        """Consume one execution ticket and produce optional AI feedback."""

        try:
            evaluation_id, learner_id = self._validate_evaluation_payload(payload)
        except ValidationError as error:
            return ApiResponse(400, {"error": str(error)})

        pending = self._take_evaluation(evaluation_id, learner_id)
        if pending is None:
            return ApiResponse(404, {"error": "评析任务不存在或已经过期。"})

        evaluation_started = perf_counter()
        feedback, ai_body = self._evaluate(
            pending.source,
            pending.result,
            pending.assessment,
            pending.learner_id,
        )
        evaluation_round_trip_ms = round((perf_counter() - evaluation_started) * 1_000)
        record_body: dict[str, Any] | None = None
        if (
            pending.record_id is not None
            and pending.learner_id is not None
            and self._record_store is not None
        ):
            try:
                record = self._record_store.update_feedback(
                    pending.record_id,
                    pending.learner_id,
                    ai_status=ai_body["status"],
                    feedback=feedback,
                )
                record_body = None if record is None else record.as_dict()
            except (OSError, ValueError, sqlite3.Error):
                record_body = {"status": "unavailable"}
        return ApiResponse(
            200,
            {
                "ai": ai_body,
                "record": record_body,
                "serviceTiming": {"evaluationRoundTripMs": evaluation_round_trip_ms},
            },
        )

    def learning_records(self, learner_id: str | None) -> ApiResponse:
        """Return privacy-minimized records for one anonymous browser identity."""

        try:
            normalized_id = self._validate_learner_id(learner_id, required=True)
        except ValidationError as error:
            return ApiResponse(400, {"error": str(error)})
        if self._record_store is None:
            return ApiResponse(503, {"error": "学习记录服务暂时不可用。"})
        try:
            records = self._record_store.list_for(normalized_id)
        except (OSError, ValueError, sqlite3.Error):
            return ApiResponse(503, {"error": "学习记录服务暂时不可用。"})
        return ApiResponse(200, {"records": [record.as_dict() for record in records]})

    def _validate_payload(self, payload: Any) -> tuple[str, str, str | None, bool]:
        if not isinstance(payload, dict):
            raise ValidationError("请求体必须是 JSON 对象。")

        language = payload.get("language", "python")
        if language != "python":
            raise ValidationError("当前版本只支持 Python。")

        source = payload.get("source")
        stdin = payload.get("stdin", "")
        ai_enabled = payload.get("enableAi", True)
        learner_id = self._validate_learner_id(payload.get("learnerId"), required=False)
        if not isinstance(source, str) or not source.strip():
            raise ValidationError("请输入需要运行的 Python 代码。")
        if not isinstance(stdin, str):
            raise ValidationError("标准输入必须是文本。")
        if not isinstance(ai_enabled, bool):
            raise ValidationError("enableAi 必须是布尔值。")
        if "\x00" in source or "\x00" in stdin:
            raise ValidationError("代码和标准输入不能包含空字节。")
        if len(source.encode("utf-8")) > self._settings.max_source_bytes:
            raise ValidationError(
                f"代码不能超过 {self._settings.max_source_bytes // 1024} KiB。"
            )
        if len(stdin.encode("utf-8")) > self._settings.max_stdin_bytes:
            raise ValidationError(
                f"标准输入不能超过 {self._settings.max_stdin_bytes // 1024} KiB。"
            )
        return source, stdin, learner_id, ai_enabled

    def _validate_evaluation_payload(self, payload: Any) -> tuple[str, str | None]:
        if not isinstance(payload, dict):
            raise ValidationError("请求体必须是 JSON 对象。")
        evaluation_id = payload.get("evaluationId")
        if not isinstance(evaluation_id, str):
            raise ValidationError("evaluationId 必须是 UUID 字符串。")
        try:
            parsed = UUID(evaluation_id)
        except ValueError as exc:
            raise ValidationError("evaluationId 必须是有效的 UUID。") from exc
        if parsed.version != 4:
            raise ValidationError("evaluationId 必须是 UUID v4。")
        learner_id = self._validate_learner_id(payload.get("learnerId"), required=False)
        return str(parsed), learner_id

    def _queue_evaluation(
        self,
        source: str,
        result: ExecutionResult,
        assessment: RuleAssessment,
        learner_id: str | None,
        record_id: str | None,
    ) -> str:
        evaluation_id = str(uuid4())
        now = monotonic()
        pending = PendingEvaluation(
            source,
            result,
            assessment,
            learner_id,
            record_id,
            now,
        )
        with self._pending_lock:
            self._discard_expired_evaluations(now)
            while len(self._pending_evaluations) >= MAX_PENDING_EVALUATIONS:
                oldest_id = next(iter(self._pending_evaluations))
                self._pending_evaluations.pop(oldest_id)
            self._pending_evaluations[evaluation_id] = pending
        return evaluation_id

    def _take_evaluation(
        self, evaluation_id: str, learner_id: str | None
    ) -> PendingEvaluation | None:
        with self._pending_lock:
            self._discard_expired_evaluations(monotonic())
            pending = self._pending_evaluations.get(evaluation_id)
            if pending is None or pending.learner_id != learner_id:
                return None
            return self._pending_evaluations.pop(evaluation_id)

    def _discard_expired_evaluations(self, now: float) -> None:
        expired = [
            evaluation_id
            for evaluation_id, pending in self._pending_evaluations.items()
            if now - pending.created_at > PENDING_EVALUATION_TTL_SECONDS
        ]
        for evaluation_id in expired:
            self._pending_evaluations.pop(evaluation_id, None)

    def _evaluate(
        self,
        source: str,
        result: ExecutionResult,
        assessment: RuleAssessment,
        learner_id: str | None,
    ) -> tuple[AiFeedback | None, dict[str, Any]]:
        if assessment.category == "system_error":
            return None, {
                "status": "skipped",
                "message": "执行环境异常，不对学生代码生成 AI 评价。",
            }
        if self._evaluator is None:
            return None, {"status": self._ai_status, "message": self._ai_message}
        try:
            feedback = self._evaluator.evaluate(source, result, assessment, learner_id)
        except AiEvaluationError:
            return None, {
                "status": "unavailable",
                "message": "AI 反馈暂时不可用；规则结论和学习记录不受影响。",
            }
        return feedback, feedback.as_dict()

    @staticmethod
    def _validate_learner_id(value: Any, *, required: bool) -> str | None:
        if value is None and not required:
            return None
        if not isinstance(value, str):
            raise ValidationError("learnerId 必须是 UUID 字符串。")
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValidationError("learnerId 必须是有效的 UUID。") from exc
        if parsed.version != 4:
            raise ValidationError("learnerId 必须是随机生成的 UUID v4。")
        return str(parsed)
