"""Persist local paper drafts, reviews and revision previews.

Revision ID: research_paper_workflow_v1
Revises: research_experiment_evidence_v1
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_paper_workflow_v1"
down_revision: str | None = "research_experiment_evidence_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, columns, indexes in (
        (
            "research_paper_drafts",
            [
                sa.Column("id", sa.String(length=36), primary_key=True),
                sa.Column("conversation_id", sa.String(length=36), nullable=False),
                sa.Column("draft_data", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
            ],
            ["conversation_id"],
        ),
        (
            "research_paper_reviews",
            [
                sa.Column("id", sa.String(length=36), primary_key=True),
                sa.Column("draft_id", sa.String(length=36), nullable=False),
                sa.Column("conversation_id", sa.String(length=36), nullable=False),
                sa.Column("review_data", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
            ],
            ["draft_id", "conversation_id"],
        ),
        (
            "research_paper_revisions",
            [
                sa.Column("id", sa.String(length=36), primary_key=True),
                sa.Column("parent_draft_id", sa.String(length=36), nullable=False),
                sa.Column("review_id", sa.String(length=36), nullable=False),
                sa.Column("revision_data", sa.JSON(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
            ],
            ["parent_draft_id", "review_id"],
        ),
    ):
        op.create_table(name, *columns)
        for column in indexes:
            op.create_index(f"ix_{name}_{column}", name, [column])


def downgrade() -> None:
    for name, indexes in (
        ("research_paper_revisions", ["parent_draft_id", "review_id"]),
        ("research_paper_reviews", ["draft_id", "conversation_id"]),
        ("research_paper_drafts", ["conversation_id"]),
    ):
        for column in indexes:
            op.drop_index(f"ix_{name}_{column}", table_name=name)
        op.drop_table(name)
