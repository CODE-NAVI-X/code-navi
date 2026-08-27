"""Persist locally generated research reproduction Pipelines.

Revision ID: reproduction_pipelines_v1
Revises: research_citation_quality_v1
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "reproduction_pipelines_v1"
down_revision: str | None = "research_citation_quality_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_reproduction_pipelines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_research_reproduction_pipelines_conversation_id",
        "research_reproduction_pipelines",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_reproduction_pipelines_conversation_id",
        table_name="research_reproduction_pipelines",
    )
    op.drop_table("research_reproduction_pipelines")
