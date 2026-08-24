"""Persist Practice launch contexts and safe outcomes.

Revision ID: practice_launch_outcomes_v1
Revises: integrated_feature_heads_v1
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "practice_launch_outcomes_v1"
down_revision: str | None = "integrated_feature_heads_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_launches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("local_profile_id", sa.String(length=64), nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("source_activity_id", sa.String(length=36), nullable=True),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("focus_type", sa.String(length=64), nullable=True),
        sa.Column("focus_id", sa.String(length=128), nullable=True),
        sa.Column("focus_label", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_activity_id"],
            ["workspace_activities.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["workspace_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_practice_launches_owner_created_at",
        "practice_launches",
        ["local_profile_id", "created_at"],
    )
    op.create_index(
        "ix_practice_launches_workspace_created_at",
        "practice_launches",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "practice_outcomes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("launch_id", sa.String(length=36), nullable=False),
        sa.Column("local_profile_id", sa.String(length=64), nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("problem_id", sa.String(length=128), nullable=True),
        sa.Column("problem_version", sa.String(length=32), nullable=True),
        sa.Column("verdict", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("score", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.String(length=512), nullable=False),
        sa.Column("safe_result_data", sa.Text(), nullable=False),
        sa.Column("knowledge_gap_kind", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["launch_id"], ["practice_launches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["workspace_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "launch_id",
            "mode",
            "idempotency_key",
            name="uq_practice_outcomes_launch_mode_idem",
        ),
    )
    op.create_index(
        "ix_practice_outcomes_launch_created_at",
        "practice_outcomes",
        ["launch_id", "created_at"],
    )
    op.create_index(
        "ix_practice_outcomes_workspace_created_at",
        "practice_outcomes",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_practice_outcomes_learner_created_at",
        "practice_outcomes",
        ["learner_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_practice_outcomes_learner_created_at", table_name="practice_outcomes")
    op.drop_index("ix_practice_outcomes_workspace_created_at", table_name="practice_outcomes")
    op.drop_index("ix_practice_outcomes_launch_created_at", table_name="practice_outcomes")
    op.drop_table("practice_outcomes")
    op.drop_index("ix_practice_launches_workspace_created_at", table_name="practice_launches")
    op.drop_index("ix_practice_launches_owner_created_at", table_name="practice_launches")
    op.drop_table("practice_launches")
