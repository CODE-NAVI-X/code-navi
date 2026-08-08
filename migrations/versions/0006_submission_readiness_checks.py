"""Persist local rules-based submission-readiness checks.

Revision ID: research_submission_readiness_v1
Revises: research_paper_workflow_v1
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_submission_readiness_v1"
down_revision: str | None = "research_paper_workflow_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_submission_readiness_checks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("check_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_research_submission_readiness_checks_draft_id",
        "research_submission_readiness_checks",
        ["draft_id"],
    )
    op.create_index(
        "ix_research_submission_readiness_checks_conversation_id",
        "research_submission_readiness_checks",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_submission_readiness_checks_conversation_id",
        table_name="research_submission_readiness_checks",
    )
    op.drop_index(
        "ix_research_submission_readiness_checks_draft_id",
        table_name="research_submission_readiness_checks",
    )
    op.drop_table("research_submission_readiness_checks")
