"""Persist user-selected evidence citation placeholders.

Revision ID: research_citation_scaffold_v1
Revises: research_revision_suggestions_v1
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_citation_scaffold_v1"
down_revision: str | None = "research_revision_suggestions_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_selected_citations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("selection_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_research_selected_citations_conversation_id",
        "research_selected_citations",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_selected_citations_conversation_id",
        table_name="research_selected_citations",
    )
    op.drop_table("research_selected_citations")
