"""Persist user-confirmable paragraph revision candidates.

Revision ID: research_revision_suggestions_v1
Revises: research_submission_readiness_v1
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_revision_suggestions_v1"
down_revision: str | None = "research_submission_readiness_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_revision_suggestions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("revision_task_id", sa.String(length=36), nullable=False),
        sa.Column("suggestion_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for column in ("draft_id", "review_id", "revision_task_id"):
        op.create_index(
            f"ix_research_revision_suggestions_{column}",
            "research_revision_suggestions",
            [column],
        )


def downgrade() -> None:
    for column in ("revision_task_id", "review_id", "draft_id"):
        op.drop_index(
            f"ix_research_revision_suggestions_{column}",
            table_name="research_revision_suggestions",
        )
    op.drop_table("research_revision_suggestions")
