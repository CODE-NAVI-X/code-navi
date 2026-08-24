"""SQLAlchemy models for Practice launch contexts and safe outcomes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint

from code_navi.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class PracticeLaunchModel(Base):
    """A server-issued opaque context for one or more Practice operations."""

    __tablename__ = "practice_launches"
    __table_args__ = (
        Index("ix_practice_launches_owner_created_at", "local_profile_id", "created_at"),
        Index("ix_practice_launches_workspace_created_at", "workspace_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    local_profile_id = Column(String(64), nullable=False)
    learner_id = Column(String(36), nullable=False)
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
    source_activity_id = Column(
        String(36),
        ForeignKey("workspace_activities.id", ondelete="SET NULL"),
        nullable=True,
    )
    capability = Column(String(32), nullable=False, default="practice")
    mode = Column(String(32), nullable=False, default="free_run")
    focus_type = Column(String(64), nullable=True)
    focus_id = Column(String(128), nullable=True)
    focus_label = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    expires_at = Column(DateTime, nullable=False)


class PracticeOutcomeModel(Base):
    """A privacy-minimized authoritative Practice result.

    The stored payload deliberately omits source code, stdin, hidden-test
    content, and raw stdout/stderr.  Those fields stay in the execution response
    only and are not persisted as Workspace sources.
    """

    __tablename__ = "practice_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "launch_id",
            "mode",
            "idempotency_key",
            name="uq_practice_outcomes_launch_mode_idem",
        ),
        Index("ix_practice_outcomes_launch_created_at", "launch_id", "created_at"),
        Index("ix_practice_outcomes_workspace_created_at", "workspace_id", "created_at"),
        Index("ix_practice_outcomes_learner_created_at", "learner_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    launch_id = Column(
        String(36),
        ForeignKey("practice_launches.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_profile_id = Column(String(64), nullable=False)
    learner_id = Column(String(36), nullable=False)
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
    mode = Column(String(32), nullable=False)
    idempotency_key = Column(String(64), nullable=True)
    problem_id = Column(String(128), nullable=True)
    problem_version = Column(String(32), nullable=True)
    verdict = Column(String(64), nullable=False)
    category = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False)
    score = Column(String(32), nullable=True)
    summary = Column(String(512), nullable=False)
    safe_result_data = Column(Text, nullable=False)
    knowledge_gap_kind = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)

