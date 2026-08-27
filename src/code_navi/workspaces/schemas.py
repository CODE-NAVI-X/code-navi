"""Request and response schemas for persistent Workspaces."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkspaceKind = Literal["personal", "course", "project", "research", "general"]
TaskStatus = Literal["active", "paused", "completed", "archived"]


class CreateWorkspaceRequest(BaseModel):
    """Create a non-personal Workspace for one local browser profile."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    local_profile_id: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["course", "project", "research", "general"] = "general"
    description: str | None = Field(default=None, max_length=2000)


class CreateTaskRequest(BaseModel):
    """Create a Task in an explicit Workspace or the profile's personal one."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    local_profile_id: str | None = Field(default=None, max_length=64)
    goal: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    success_criteria: list[str] = Field(default_factory=list, max_length=12)
    workspace_id: str | None = Field(default=None, min_length=1, max_length=36)


class WorkspaceResponse(BaseModel):
    """A locally scoped Workspace safe to display in navigation."""

    id: str
    title: str
    kind: WorkspaceKind
    description: str | None
    created_at: datetime
    updated_at: datetime


class TaskResponse(BaseModel):
    """A Task and its Workspace association."""

    id: str
    workspace_id: str
    title: str
    goal: str
    success_criteria: list[str]
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ActivityResponse(BaseModel):
    """A safe Activity index, never the source capability payload."""

    id: str
    workspace_id: str
    task_id: str | None
    capability: str
    action_type: str
    source_object_type: str
    source_object_id: str
    title: str
    summary: str
    created_at: datetime


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceResponse]


class TaskListResponse(BaseModel):
    items: list[TaskResponse]


class ActivityListResponse(BaseModel):
    items: list[ActivityResponse]
