"""Workspace orchestration for Practice launches and outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from code_navi.workspaces.models import TaskModel, WorkspaceActivityModel, WorkspaceModel
from code_navi.workspaces.service import (
    WorkspaceConflictError,
    WorkspaceNotFoundError,
    WorkspaceService,
)

from .models import PracticeLaunchModel, PracticeOutcomeModel

_LAUNCH_TTL = timedelta(days=7)
_MAX_FOCUS_TEXT = 512
_MAX_IDEMPOTENCY_KEY = 64
_ACTION_LAUNCH_MODES = {"execute": "free_run", "submit": "problem_submit"}
_USER_GAP_CATEGORIES = {
    "syntax_error",
    "runtime_error",
    "time_limit",
    "output_limit",
    "wrong_answer",
}
_SYSTEM_CATEGORIES = {"system_error"}


class PracticeLaunchValidationError(ValueError):
    """The launch request or launch-bound compiler request is invalid."""


class PracticeLaunchNotFoundError(LookupError):
    """The launch is absent, expired, or outside the requested owner scope."""


@dataclass(frozen=True)
class ResolvedPracticeLaunch:
    launch: PracticeLaunchModel


class PracticeIntegrationService:
    """Issue Practice launches and persist safe outcomes for Workspaces."""

    def __init__(self, workspace_service: WorkspaceService | None = None) -> None:
        self._workspace_service = workspace_service or WorkspaceService()

    def create_launch(
        self,
        payload: Any,
        db: Session,
        *,
        principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> PracticeLaunchModel:
        request = self._validate_launch_request(payload)
        context = self._workspace_service.resolve_learning_context(
            local_profile_id=request["local_profile_id"],
            workspace_id=request["workspace_id"],
            task_id=request["task_id"],
            principal_id=principal_id,
            owned_ids=owned_ids,
            db=db,
        )
        source_activity_id = request["source_activity_id"]
        if source_activity_id is not None:
            source_activity = self._get_source_activity(
                source_activity_id,
                request["local_profile_id"],
                db,
            )
            if source_activity.workspace_id != context.workspace.id:
                raise WorkspaceConflictError(
                    "Source Activity does not belong to the requested Workspace."
                )

        launch = PracticeLaunchModel(
            local_profile_id=request["local_profile_id"],
            owner_principal_id=principal_id,
            learner_id=request["learner_id"],
            workspace_id=context.workspace.id,
            task_id=context.task.id if context.task else None,
            source_activity_id=source_activity_id,
            capability="practice",
            mode=request["mode"],
            focus_type=request["focus_type"],
            focus_id=request["focus_id"],
            focus_label=request["focus_label"],
            expires_at=datetime.now(UTC) + _LAUNCH_TTL,
        )
        db.add(launch)
        db.commit()
        db.refresh(launch)
        return launch

    def resolve_launch_for_payload(
        self,
        payload: Any,
        *,
        action: str,
        db: Session,
    ) -> ResolvedPracticeLaunch | None:
        if not isinstance(payload, dict):
            return None
        raw_launch_id = payload.get("launchId")
        if raw_launch_id is None:
            return None
        launch_id = self._uuid(raw_launch_id, "launchId")
        self._attempt_id(payload)
        launch = db.query(PracticeLaunchModel).filter(PracticeLaunchModel.id == launch_id).first()
        if launch is None or self._expired(launch.expires_at):
            raise PracticeLaunchNotFoundError("Practice launch not found.")
        expected_mode = _ACTION_LAUNCH_MODES.get(action)
        if expected_mode is None or launch.mode != expected_mode:
            raise PracticeLaunchValidationError("launch mode does not match the compiler action.")
        learner_id = payload.get("learnerId")
        if learner_id is not None and self._uuid(learner_id, "learnerId") != launch.learner_id:
            raise PracticeLaunchValidationError("learnerId does not match the launch.")
        workspace = (
            db.query(WorkspaceModel)
            .filter(
                WorkspaceModel.id == launch.workspace_id,
                WorkspaceModel.owner_scope_id == launch.local_profile_id,
            )
            .first()
        )
        if workspace is None:
            raise PracticeLaunchNotFoundError("Practice launch not found.")
        if launch.task_id is not None:
            task = (
                db.query(TaskModel)
                .filter(
                    TaskModel.id == launch.task_id,
                    TaskModel.workspace_id == launch.workspace_id,
                )
                .first()
            )
            if task is None:
                raise PracticeLaunchNotFoundError("Practice launch not found.")
        return ResolvedPracticeLaunch(launch=launch)

    def record_execute_outcome(
        self,
        *,
        launch: PracticeLaunchModel,
        response_body: dict[str, Any],
        request_payload: Any,
        db: Session,
    ) -> PracticeOutcomeModel | None:
        assessment = response_body.get("assessment")
        if not isinstance(assessment, dict):
            return None
        category = self._text(assessment.get("category"), default="unknown", max_length=64)
        if category in _SYSTEM_CATEGORIES:
            return None
        idempotency_key = self._idempotency_key(request_payload)
        safe_data = {
            "kind": "compiler_execute.v1",
            "outcome": self._text(response_body.get("outcome"), default=category, max_length=64),
            "assessment": {
                "category": category,
                "severity": self._text(assessment.get("severity"), default="info", max_length=32),
                "title": self._text(assessment.get("title"), default="Practice", max_length=128),
                "summary": self._text(assessment.get("summary"), default="", max_length=512),
                "errorType": self._optional_text(assessment.get("errorType"), max_length=128),
                "line": assessment.get("line") if isinstance(assessment.get("line"), int) else None,
                "source": "deterministic_rule",
            },
            "runtime": self._safe_runtime(response_body.get("runtime")),
            "metrics": self._safe_metrics(response_body.get("metrics")),
        }
        outcome = PracticeOutcomeModel(
            launch_id=launch.id,
            owner_principal_id=launch.owner_principal_id,
            local_profile_id=launch.local_profile_id,
            learner_id=launch.learner_id,
            workspace_id=launch.workspace_id,
            task_id=launch.task_id,
            mode="execute",
            idempotency_key=idempotency_key,
            verdict=self._text(response_body.get("outcome"), default=category, max_length=64),
            category=category,
            severity=safe_data["assessment"]["severity"],
            summary=safe_data["assessment"]["summary"] or safe_data["assessment"]["title"],
            safe_result_data=json.dumps(safe_data, ensure_ascii=False),
            knowledge_gap_kind=self._knowledge_gap_kind(category),
        )
        return self._insert_outcome_and_activity(
            outcome,
            title=self._activity_title(launch, "Practice 运行"),
            db=db,
        )

    def record_submit_outcome(
        self,
        *,
        launch: PracticeLaunchModel,
        response_body: dict[str, Any],
        request_payload: Any,
        db: Session,
    ) -> PracticeOutcomeModel | None:
        verdict = self._text(response_body.get("verdict"), default="unknown", max_length=64)
        if verdict in _SYSTEM_CATEGORIES:
            return None
        category = "success" if verdict == "accepted" else verdict
        if category in _SYSTEM_CATEGORIES:
            return None
        idempotency_key = self._idempotency_key(request_payload)
        safe_tests = []
        for item in response_body.get("testResults", []):
            if not isinstance(item, dict):
                continue
            safe_tests.append(
                {
                    "index": item.get("index") if isinstance(item.get("index"), int) else None,
                    "status": self._text(item.get("status"), default="unknown", max_length=64),
                    "points": item.get("points") if isinstance(item.get("points"), int) else None,
                    "hidden": item.get("hidden") is True,
                }
            )
        raw_score = response_body.get("score")
        raw_passed = response_body.get("passed")
        raw_total = response_body.get("total")
        safe_data = {
            "kind": "compiler_submit.v1",
            "verdict": verdict,
            "score": raw_score if isinstance(raw_score, int | float) else None,
            "passed": raw_passed if isinstance(raw_passed, int) else None,
            "total": raw_total if isinstance(raw_total, int) else None,
            "passedPoints": (
                response_body.get("passedPoints")
                if isinstance(response_body.get("passedPoints"), int)
                else None
            ),
            "totalPoints": (
                response_body.get("totalPoints")
                if isinstance(response_body.get("totalPoints"), int)
                else None
            ),
            "testResults": safe_tests,
        }
        summary = self._submit_summary(safe_data)
        outcome = PracticeOutcomeModel(
            launch_id=launch.id,
            owner_principal_id=launch.owner_principal_id,
            local_profile_id=launch.local_profile_id,
            learner_id=launch.learner_id,
            workspace_id=launch.workspace_id,
            task_id=launch.task_id,
            mode="submit",
            idempotency_key=idempotency_key,
            problem_id=self._optional_text(response_body.get("problemId"), max_length=128),
            problem_version=self._optional_scalar_text(
                response_body.get("problemVersion"),
                max_length=32,
            ),
            verdict=verdict,
            category=category,
            severity="success" if verdict == "accepted" else "error",
            score=str(safe_data["score"]) if safe_data["score"] is not None else None,
            summary=summary,
            safe_result_data=json.dumps(safe_data, ensure_ascii=False),
            knowledge_gap_kind=self._knowledge_gap_kind(category),
        )
        return self._insert_outcome_and_activity(
            outcome,
            title=self._activity_title(launch, "Practice 提交"),
            db=db,
        )

    def get_outcome(
        self,
        *,
        outcome_id: str,
        local_profile_id: str | None = None,
        owned_ids: list[str] | None = None,
        db: Session,
    ) -> PracticeOutcomeModel:
        parsed_outcome_id = self._uuid(outcome_id, "outcomeId")
        query = db.query(PracticeOutcomeModel).filter(
            PracticeOutcomeModel.id == parsed_outcome_id
        )
        if owned_ids:
            query = query.filter(PracticeOutcomeModel.owner_principal_id.in_(owned_ids))
        elif local_profile_id:
            query = query.filter(PracticeOutcomeModel.local_profile_id == local_profile_id)
        outcome = query.first()
        if outcome is None:
            raise PracticeLaunchNotFoundError("Practice outcome not found.")
        return outcome

    @staticmethod
    def launch_response(launch: PracticeLaunchModel) -> dict[str, Any]:
        focus = None
        if launch.focus_type or launch.focus_id or launch.focus_label:
            focus = {
                "type": launch.focus_type,
                "id": launch.focus_id,
                "label": launch.focus_label,
            }
        return {
            "launchId": launch.id,
            "localProfileId": launch.local_profile_id,
            "learnerId": launch.learner_id,
            "workspaceId": launch.workspace_id,
            "taskId": launch.task_id,
            "sourceActivityId": launch.source_activity_id,
            "capability": launch.capability,
            "mode": launch.mode,
            "focus": focus,
            "expiresAt": launch.expires_at.isoformat(),
        }

    @staticmethod
    def outcome_response(outcome: PracticeOutcomeModel) -> dict[str, Any]:
        return {
            "outcomeId": outcome.id,
            "launchId": outcome.launch_id,
            "workspaceId": outcome.workspace_id,
            "taskId": outcome.task_id,
            "mode": outcome.mode,
            "verdict": outcome.verdict,
            "category": outcome.category,
            "severity": outcome.severity,
            "summary": outcome.summary,
            "knowledgeGapKind": outcome.knowledge_gap_kind,
            "createdAt": outcome.created_at.isoformat(),
        }

    @staticmethod
    def outcome_detail_response(outcome: PracticeOutcomeModel) -> dict[str, Any]:
        body = PracticeIntegrationService.outcome_response(outcome)
        try:
            safe_result = json.loads(outcome.safe_result_data)
        except (json.JSONDecodeError, TypeError):
            safe_result = {"kind": "unknown", "summary": outcome.summary}
        body["safeResult"] = safe_result
        return body

    def _insert_outcome_and_activity(
        self,
        outcome: PracticeOutcomeModel,
        *,
        title: str,
        db: Session,
    ) -> PracticeOutcomeModel:
        existing = self._existing_outcome(outcome, db)
        if existing is not None:
            self._ensure_activity_for_outcome(existing, title=title, db=db)
            return existing
        try:
            with db.begin_nested():
                db.add(outcome)
                db.flush()
                self._add_activity_for_outcome(outcome, title=title, db=db)
                self._touch_context(outcome, db)
        except IntegrityError:
            existing = self._existing_outcome(outcome, db)
            if existing is None:
                raise
            self._ensure_activity_for_outcome(existing, title=title, db=db)
            return existing
        db.commit()
        db.refresh(outcome)
        return outcome

    def _ensure_activity_for_outcome(
        self,
        outcome: PracticeOutcomeModel,
        *,
        title: str,
        db: Session,
    ) -> WorkspaceActivityModel:
        existing = self._activity_for_outcome(outcome, db)
        if existing is not None:
            return existing
        try:
            with db.begin_nested():
                activity = self._add_activity_for_outcome(outcome, title=title, db=db)
                self._touch_context(outcome, db)
        except IntegrityError:
            existing = self._activity_for_outcome(outcome, db)
            if existing is None:
                raise
            return existing
        db.commit()
        return activity

    def _add_activity_for_outcome(
        self,
        outcome: PracticeOutcomeModel,
        *,
        title: str,
        db: Session,
    ) -> WorkspaceActivityModel:
        activity = WorkspaceActivityModel(
            workspace_id=outcome.workspace_id,
            task_id=outcome.task_id,
            capability="practice",
            action_type=outcome.mode,
            source_object_type="practice_outcome",
            source_object_id=outcome.id,
            title=title,
            summary=outcome.summary,
        )
        db.add(activity)
        db.flush()
        return activity

    @staticmethod
    def _activity_for_outcome(
        outcome: PracticeOutcomeModel,
        db: Session,
    ) -> WorkspaceActivityModel | None:
        return (
            db.query(WorkspaceActivityModel)
            .filter(
                WorkspaceActivityModel.capability == "practice",
                WorkspaceActivityModel.action_type == outcome.mode,
                WorkspaceActivityModel.source_object_type == "practice_outcome",
                WorkspaceActivityModel.source_object_id == outcome.id,
            )
            .first()
        )

    @staticmethod
    def _touch_context(outcome: PracticeOutcomeModel, db: Session) -> None:
        now = datetime.now(UTC)
        workspace = (
            db.query(WorkspaceModel).filter(WorkspaceModel.id == outcome.workspace_id).first()
        )
        if workspace is not None:
            workspace.updated_at = now
        if outcome.task_id is not None:
            task = db.query(TaskModel).filter(TaskModel.id == outcome.task_id).first()
            if task is not None:
                task.updated_at = now

    @staticmethod
    def _existing_outcome(
        outcome: PracticeOutcomeModel,
        db: Session,
    ) -> PracticeOutcomeModel | None:
        if outcome.idempotency_key is None:
            return None
        return (
            db.query(PracticeOutcomeModel)
            .filter(
                PracticeOutcomeModel.launch_id == outcome.launch_id,
                PracticeOutcomeModel.mode == outcome.mode,
                PracticeOutcomeModel.idempotency_key == outcome.idempotency_key,
            )
            .first()
        )

    def _validate_launch_request(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PracticeLaunchValidationError("request body must be a JSON object")
        local_profile_id = self._bounded_required_text(
            payload.get("localProfileId"), "localProfileId", 64
        )
        learner_id = self._uuid(payload.get("learnerId"), "learnerId")
        workspace_id = self._optional_uuid(payload.get("workspaceId"), "workspaceId")
        task_id = self._optional_uuid(payload.get("taskId"), "taskId")
        source_activity_id = self._optional_uuid(
            payload.get("sourceActivityId"), "sourceActivityId"
        )
        mode = self._optional_text(payload.get("mode"), max_length=32) or "free_run"
        if mode not in {"free_run", "problem_submit"}:
            raise PracticeLaunchValidationError("mode is invalid")
        focus_type = focus_id = focus_label = None
        focus = payload.get("focus")
        if focus is not None:
            if not isinstance(focus, dict):
                raise PracticeLaunchValidationError("focus must be an object")
            focus_type = self._optional_text(focus.get("type"), max_length=64)
            focus_id = self._optional_text(focus.get("id"), max_length=128)
            focus_label = self._optional_text(focus.get("label"), max_length=_MAX_FOCUS_TEXT)
        return {
            "local_profile_id": local_profile_id,
            "learner_id": learner_id,
            "workspace_id": workspace_id,
            "task_id": task_id,
            "source_activity_id": source_activity_id,
            "mode": mode,
            "focus_type": focus_type,
            "focus_id": focus_id,
            "focus_label": focus_label,
        }

    def _get_source_activity(
        self,
        activity_id: str,
        local_profile_id: str,
        db: Session,
    ) -> WorkspaceActivityModel:
        activity = (
            db.query(WorkspaceActivityModel)
            .join(WorkspaceModel, WorkspaceActivityModel.workspace_id == WorkspaceModel.id)
            .filter(
                WorkspaceActivityModel.id == activity_id,
                WorkspaceModel.owner_scope_id == local_profile_id,
            )
            .first()
        )
        if activity is None:
            raise WorkspaceNotFoundError(activity_id)
        return activity

    def _activity_title(self, launch: PracticeLaunchModel, fallback: str) -> str:
        if launch.focus_label:
            return f"{fallback}: {launch.focus_label}"[:512]
        return fallback

    @staticmethod
    def _submit_summary(safe_data: dict[str, Any]) -> str:
        verdict = safe_data["verdict"]
        score = safe_data["score"]
        passed = safe_data["passed"]
        total = safe_data["total"]
        if verdict == "accepted":
            return f"题目提交通过，得分 {score}。"
        if passed is not None and total is not None:
            return f"题目提交未通过，{passed}/{total} 个测试通过，得分 {score}。"
        return "题目提交未通过。"

    @staticmethod
    def _expired(expires_at: datetime) -> bool:
        current = datetime.now(UTC)
        if expires_at.tzinfo is None:
            current = current.replace(tzinfo=None)
        return expires_at < current

    @staticmethod
    def _safe_runtime(value: Any) -> dict[str, str | None]:
        if not isinstance(value, dict):
            return {"language": None, "version": None}
        return {
            "language": PracticeIntegrationService._optional_text(
                value.get("language"),
                max_length=32,
            ),
            "version": PracticeIntegrationService._optional_text(
                value.get("version"),
                max_length=32,
            ),
        }

    @staticmethod
    def _safe_metrics(value: Any) -> dict[str, int | None]:
        if not isinstance(value, dict):
            return {"wallTimeMs": None, "cpuTimeMs": None, "memoryBytes": None}
        raw_wall_time = value.get("wallTimeMs")
        raw_cpu_time = value.get("cpuTimeMs")
        raw_memory = value.get("memoryBytes")
        return {
            "wallTimeMs": raw_wall_time if isinstance(raw_wall_time, int) else None,
            "cpuTimeMs": raw_cpu_time if isinstance(raw_cpu_time, int) else None,
            "memoryBytes": raw_memory if isinstance(raw_memory, int) else None,
        }

    @staticmethod
    def _idempotency_key(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        return PracticeIntegrationService._attempt_id(payload)

    @staticmethod
    def _attempt_id(payload: dict[str, Any]) -> str:
        value = payload.get("attemptId")
        if value is None:
            raise PracticeLaunchValidationError("attemptId is required when launchId is provided")
        if not isinstance(value, str) or len(value) > _MAX_IDEMPOTENCY_KEY:
            raise PracticeLaunchValidationError("attemptId must be a UUID v4")
        try:
            parsed = UUID(value)
        except ValueError as error:
            raise PracticeLaunchValidationError("attemptId must be a UUID v4") from error
        if parsed.version != 4:
            raise PracticeLaunchValidationError("attemptId must be a UUID v4")
        return str(parsed)

    @staticmethod
    def _knowledge_gap_kind(category: str) -> str | None:
        if category == "compile_error":
            return "syntax_error"
        return category if category in _USER_GAP_CATEGORIES else None

    @staticmethod
    def _optional_uuid(value: Any, field: str) -> str | None:
        if value is None:
            return None
        return PracticeIntegrationService._uuid(value, field)

    @staticmethod
    def _uuid(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise PracticeLaunchValidationError(f"{field} must be a UUID string")
        try:
            parsed = UUID(value)
        except ValueError as error:
            raise PracticeLaunchValidationError(f"{field} must be a valid UUID") from error
        if parsed.version != 4:
            raise PracticeLaunchValidationError(f"{field} must be a UUID v4")
        return str(parsed)

    @staticmethod
    def _bounded_required_text(value: Any, field: str, max_length: int) -> str:
        text = PracticeIntegrationService._optional_text(value, max_length=max_length)
        if text is None:
            raise PracticeLaunchValidationError(f"{field} is required")
        return text

    @staticmethod
    def _optional_text(value: Any, *, max_length: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text or "\x00" in text:
            return None
        return text[:max_length]

    @staticmethod
    def _optional_scalar_text(value: Any, *, max_length: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str | int | float):
            return None
        return PracticeIntegrationService._optional_text(str(value), max_length=max_length)

    @staticmethod
    def _text(value: Any, *, default: str, max_length: int) -> str:
        return PracticeIntegrationService._optional_text(value, max_length=max_length) or default


__all__ = [
    "PracticeIntegrationService",
    "PracticeLaunchNotFoundError",
    "PracticeLaunchValidationError",
]
