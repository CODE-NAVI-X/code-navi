"""Persist reproduction project evaluations and improvement tasks.

Revision ID: reproduction_project_evaluation_v1
Revises: reproduction_pipelines_v1
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "reproduction_project_evaluation_v1"
down_revision: str | None = "reproduction_pipelines_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_reproduction_evaluations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_research_reproduction_evaluations_conversation_id",
        "research_reproduction_evaluations",
        ["conversation_id"],
    )
    op.create_table(
        "research_reproduction_improvement_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("evaluation_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("task_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_research_reproduction_improvement_tasks_evaluation_id",
        "research_reproduction_improvement_tasks",
        ["evaluation_id"],
    )
    op.create_index(
        "ix_research_reproduction_improvement_tasks_conversation_id",
        "research_reproduction_improvement_tasks",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_reproduction_improvement_tasks_conversation_id",
        table_name="research_reproduction_improvement_tasks",
    )
    op.drop_index(
        "ix_research_reproduction_improvement_tasks_evaluation_id",
        table_name="research_reproduction_improvement_tasks",
    )
    op.drop_table("research_reproduction_improvement_tasks")
    op.drop_index(
        "ix_research_reproduction_evaluations_conversation_id",
        table_name="research_reproduction_evaluations",
    )
    op.drop_table("research_reproduction_evaluations")
