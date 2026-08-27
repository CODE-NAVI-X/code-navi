"""Persist the first Workspace, Task, and Learning Activity slice.

Revision ID: persistent_workspace_foundation_v1
Revises: research_citation_quality_v1
Create Date: 2026-08-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "persistent_workspace_foundation_v1"
down_revision: str | None = "research_citation_quality_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_scope_id", sa.String(length=64), nullable=False),
        sa.Column("personal_owner_scope_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "personal_owner_scope_id",
            name="uq_workspaces_personal_owner_scope",
        ),
    )
    op.create_index(
        "ix_workspaces_owner_scope_updated_at",
        "workspaces",
        ["owner_scope_id", "updated_at"],
    )

    op.create_table(
        "workspace_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("success_criteria", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_tasks_workspace_updated_at",
        "workspace_tasks",
        ["workspace_id", "updated_at"],
    )

    op.create_table(
        "workspace_activities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("source_object_type", sa.String(length=64), nullable=False),
        sa.Column("source_object_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["workspace_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "capability",
            "action_type",
            "source_object_type",
            "source_object_id",
            name="uq_workspace_activities_source_action",
        ),
    )
    op.create_index(
        "ix_workspace_activities_workspace_created_at",
        "workspace_activities",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_workspace_activities_task_created_at",
        "workspace_activities",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_activities_task_created_at", table_name="workspace_activities")
    op.drop_index("ix_workspace_activities_workspace_created_at", table_name="workspace_activities")
    op.drop_table("workspace_activities")
    op.drop_index("ix_workspace_tasks_workspace_updated_at", table_name="workspace_tasks")
    op.drop_table("workspace_tasks")
    op.drop_index("ix_workspaces_owner_scope_updated_at", table_name="workspaces")
    op.drop_table("workspaces")
