"""Business rules for Workspace, Task, and Activity persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from code_navi.learning.models import NotebookItemModel

from .models import TaskModel, WorkspaceActivityModel, WorkspaceModel
from .schemas import (
    ActivityResponse,
    CreateTaskRequest,
    CreateWorkspaceRequest,
    TaskResponse,
    WorkspaceResponse,
)

_PERSONAL_WORKSPACE_TITLE = "个人工作区"
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 50


class WorkspaceNotFoundError(LookupError):
    """The Workspace is absent from the current local browser profile."""


class TaskNotFoundError(LookupError):
    """The Task is absent from the current local browser profile."""


class WorkspaceConflictError(ValueError):
    """A Task and Workspace do not describe one consistent context."""


@dataclass(frozen=True)
class LearningWorkspaceContext:
    """Verified orchestration context used while persisting a Learning result."""

    workspace: WorkspaceModel
    task: TaskModel | None


class WorkspaceService:
    """Own local-profile scoping and source-derived Activity rules."""

    def get_or_create_personal_workspace(
        self,
        local_profile_id: str,
        db: Session,
    ) -> WorkspaceModel:
        existing = self._personal_workspace(local_profile_id, db)
        if existing is not None:
            return existing

        candidate = WorkspaceModel(
            owner_scope_id=local_profile_id,
            personal_owner_scope_id=local_profile_id,
            title=_PERSONAL_WORKSPACE_TITLE,
            kind="personal",
        )
        try:
            # The savepoint keeps an unrelated caller transaction intact if a
            # second browser request creates the same personal Workspace first.
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self._personal_workspace(local_profile_id, db)
            if existing is not None:
                return existing
            raise
        return candidate

    def create_workspace(
        self,
        request: CreateWorkspaceRequest,
        db: Session,
    ) -> WorkspaceResponse:
        workspace = WorkspaceModel(
            owner_scope_id=request.local_profile_id,
            title=request.title,
            kind=request.kind,
            description=request.description,
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        return self.workspace_response(workspace)

    def list_workspaces(
        self,
        local_profile_id: str,
        db: Session,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[WorkspaceResponse]:
        return [
            self.workspace_response(workspace)
            for workspace in (
                db.query(WorkspaceModel)
                .filter(WorkspaceModel.owner_scope_id == local_profile_id)
                .order_by(WorkspaceModel.updated_at.desc(), WorkspaceModel.id.desc())
                .offset(offset)
                .limit(self._limit(limit))
                .all()
            )
        ]

    def get_workspace(
        self,
        workspace_id: str,
        local_profile_id: str,
        db: Session,
    ) -> WorkspaceModel:
        workspace = (
            db.query(WorkspaceModel)
            .filter(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.owner_scope_id == local_profile_id,
            )
            .first()
        )
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)
        return workspace

    def create_task(self, request: CreateTaskRequest, db: Session) -> TaskResponse:
        workspace = (
            self.get_workspace(request.workspace_id, request.local_profile_id, db)
            if request.workspace_id
            else self.get_or_create_personal_workspace(request.local_profile_id, db)
        )
        title = request.title or request.goal[:200]
        task = TaskModel(
            workspace_id=workspace.id,
            title=title,
            goal=request.goal,
            success_criteria=json.dumps(request.success_criteria, ensure_ascii=False),
            status="active",
        )
        workspace.updated_at = datetime.now(UTC)
        db.add(task)
        db.commit()
        db.refresh(task)
        return self.task_response(task)

    def get_task(self, task_id: str, local_profile_id: str, db: Session) -> TaskModel:
        task = (
            db.query(TaskModel)
            .join(WorkspaceModel, TaskModel.workspace_id == WorkspaceModel.id)
            .filter(
                TaskModel.id == task_id,
                WorkspaceModel.owner_scope_id == local_profile_id,
            )
            .first()
        )
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def list_workspace_tasks(
        self,
        workspace_id: str,
        local_profile_id: str,
        db: Session,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[TaskResponse]:
        self.get_workspace(workspace_id, local_profile_id, db)
        return [
            self.task_response(task)
            for task in (
                db.query(TaskModel)
                .filter(TaskModel.workspace_id == workspace_id)
                .order_by(TaskModel.updated_at.desc(), TaskModel.id.desc())
                .offset(offset)
                .limit(self._limit(limit))
                .all()
            )
        ]

    def list_recent_tasks(
        self,
        local_profile_id: str,
        db: Session,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> list[TaskResponse]:
        return [
            self.task_response(task)
            for task in (
                db.query(TaskModel)
                .join(WorkspaceModel, TaskModel.workspace_id == WorkspaceModel.id)
                .filter(WorkspaceModel.owner_scope_id == local_profile_id)
                .order_by(TaskModel.updated_at.desc(), TaskModel.id.desc())
                .limit(self._limit(limit))
                .all()
            )
        ]

    def list_workspace_activities(
        self,
        workspace_id: str,
        local_profile_id: str,
        db: Session,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[ActivityResponse]:
        self.get_workspace(workspace_id, local_profile_id, db)
        return self._activities_for(
            db.query(WorkspaceActivityModel).filter(
                WorkspaceActivityModel.workspace_id == workspace_id
            ),
            limit,
            offset,
        )

    def list_task_activities(
        self,
        task_id: str,
        local_profile_id: str,
        db: Session,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> list[ActivityResponse]:
        self.get_task(task_id, local_profile_id, db)
        return self._activities_for(
            db.query(WorkspaceActivityModel).filter(WorkspaceActivityModel.task_id == task_id),
            limit,
            offset,
        )

    def resolve_learning_context(
        self,
        *,
        local_profile_id: str,
        workspace_id: str | None,
        task_id: str | None,
        db: Session,
    ) -> LearningWorkspaceContext:
        task = self.get_task(task_id, local_profile_id, db) if task_id else None
        if task is not None:
            if workspace_id and workspace_id != task.workspace_id:
                raise WorkspaceConflictError("Task does not belong to the requested Workspace.")
            workspace = self.get_workspace(task.workspace_id, local_profile_id, db)
            return LearningWorkspaceContext(workspace=workspace, task=task)

        if workspace_id:
            return LearningWorkspaceContext(
                workspace=self.get_workspace(workspace_id, local_profile_id, db),
                task=None,
            )
        return LearningWorkspaceContext(
            workspace=self.get_or_create_personal_workspace(local_profile_id, db),
            task=None,
        )

    def record_learning_activity(
        self,
        *,
        context: LearningWorkspaceContext,
        notebook_item: NotebookItemModel,
        db: Session,
    ) -> WorkspaceActivityModel:
        """Derive one safe Activity from a persisted Learning Notebook item.

        This method intentionally accepts a server-owned Notebook item instead
        of client input.  No endpoint permits a browser to declare Activity
        success directly.
        """
        existing = (
            db.query(WorkspaceActivityModel)
            .filter(
                WorkspaceActivityModel.capability == "learning",
                WorkspaceActivityModel.action_type == "knowledge_explained",
                WorkspaceActivityModel.source_object_type == "notebook_item",
                WorkspaceActivityModel.source_object_id == notebook_item.id,
            )
            .first()
        )
        if existing is not None:
            if (
                existing.workspace_id != context.workspace.id
                or existing.task_id != (context.task.id if context.task else None)
            ):
                raise WorkspaceConflictError("Learning source already belongs to another context.")
            return existing

        activity = WorkspaceActivityModel(
            workspace_id=context.workspace.id,
            task_id=context.task.id if context.task else None,
            capability="learning",
            action_type="knowledge_explained",
            source_object_type="notebook_item",
            source_object_id=notebook_item.id,
            title=notebook_item.knowledge_id,
            summary=f"已保存“{notebook_item.knowledge_id}”的知识解析。",
        )
        try:
            # A duplicate can only arise when the same persisted source is
            # retried concurrently. Keep the caller's Notebook transaction and
            # re-read the winner instead of surfacing a uniqueness failure.
            with db.begin_nested():
                db.add(activity)
                db.flush()
        except IntegrityError as error:
            existing = (
                db.query(WorkspaceActivityModel)
                .filter(
                    WorkspaceActivityModel.capability == "learning",
                    WorkspaceActivityModel.action_type == "knowledge_explained",
                    WorkspaceActivityModel.source_object_type == "notebook_item",
                    WorkspaceActivityModel.source_object_id == notebook_item.id,
                )
                .first()
            )
            if existing is None:
                raise
            if (
                existing.workspace_id != context.workspace.id
                or existing.task_id != (context.task.id if context.task else None)
            ):
                raise WorkspaceConflictError(
                    "Learning source already belongs to another context."
                ) from error
            return existing
        now = datetime.now(UTC)
        context.workspace.updated_at = now
        if context.task is not None:
            context.task.updated_at = now
        return activity

    @staticmethod
    def workspace_response(workspace: WorkspaceModel) -> WorkspaceResponse:
        return WorkspaceResponse(
            id=workspace.id,
            title=workspace.title,
            kind=workspace.kind,
            description=workspace.description,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )

    @staticmethod
    def task_response(task: TaskModel) -> TaskResponse:
        criteria = json.loads(task.success_criteria or "[]")
        return TaskResponse(
            id=task.id,
            workspace_id=task.workspace_id,
            title=task.title,
            goal=task.goal,
            success_criteria=criteria if isinstance(criteria, list) else [],
            status=task.status,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
        )

    @staticmethod
    def activity_response(activity: WorkspaceActivityModel) -> ActivityResponse:
        return ActivityResponse(
            id=activity.id,
            workspace_id=activity.workspace_id,
            task_id=activity.task_id,
            capability=activity.capability,
            action_type=activity.action_type,
            source_object_type=activity.source_object_type,
            source_object_id=activity.source_object_id,
            title=activity.title,
            summary=activity.summary,
            created_at=activity.created_at,
        )

    @staticmethod
    def _personal_workspace(local_profile_id: str, db: Session) -> WorkspaceModel | None:
        return (
            db.query(WorkspaceModel)
            .filter(WorkspaceModel.personal_owner_scope_id == local_profile_id)
            .first()
        )

    def _activities_for(self, query, limit: int, offset: int) -> list[ActivityResponse]:
        return [
            self.activity_response(activity)
            for activity in (
                query.order_by(
                    WorkspaceActivityModel.created_at.desc(),
                    WorkspaceActivityModel.id.desc(),
                )
                .offset(offset)
                .limit(self._limit(limit))
                .all()
            )
        ]

    @staticmethod
    def _limit(value: int) -> int:
        return min(max(value, 1), _MAX_LIST_LIMIT)
