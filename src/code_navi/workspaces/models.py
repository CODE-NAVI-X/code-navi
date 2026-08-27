"""SQLAlchemy models for the Workspace orchestration layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint

from code_navi.db import Base


class WorkspaceModel(Base):
    """A long-lived local organization boundary for Tasks and Activities."""

    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint(
            "personal_owner_scope_id",
            name="uq_workspaces_personal_owner_scope",
        ),
        Index("ix_workspaces_owner_scope_updated_at", "owner_scope_id", "updated_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_scope_id = Column(String(64), nullable=False)
    # Only the personal Workspace duplicates the profile id here.  The unique
    # constraint makes concurrent personal-Workspace creation idempotent while
    # allowing multiple course, project, research, or general Workspaces.
    personal_owner_scope_id = Column(String(64), nullable=True)
    title = Column(String(200), nullable=False)
    kind = Column(String(32), nullable=False, default="general")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    # Auth: principal-based ownership (nullable during compat period)
    owner_principal_id = Column(String(36), nullable=True, index=True)


class TaskModel(Base):
    """A user goal and its success criteria inside exactly one Workspace."""

    __tablename__ = "workspace_tasks"
    __table_args__ = (
        Index("ix_workspace_tasks_workspace_updated_at", "workspace_id", "updated_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    goal = Column(Text, nullable=False)
    success_criteria = Column(String, nullable=False, default="[]")
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    completed_at = Column(DateTime, nullable=True)


class WorkspaceActivityModel(Base):
    """A safe cross-module index to a persisted capability result."""

    __tablename__ = "workspace_activities"
    __table_args__ = (
        UniqueConstraint(
            "capability",
            "action_type",
            "source_object_type",
            "source_object_id",
            name="uq_workspace_activities_source_action",
        ),
        Index("ix_workspace_activities_workspace_created_at", "workspace_id", "created_at"),
        Index("ix_workspace_activities_task_created_at", "task_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id = Column(
        String(36),
        ForeignKey("workspace_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    capability = Column(String(32), nullable=False)
    action_type = Column(String(64), nullable=False)
    source_object_type = Column(String(64), nullable=False)
    source_object_id = Column(String(64), nullable=False)
    title = Column(String(512), nullable=False)
    summary = Column(String(512), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
