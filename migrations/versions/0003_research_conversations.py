"""Persist dynamic research conversations and evidence bundles

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("messages_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "research_evidence_bundles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("bundle_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_research_evidence_bundles_conversation_id",
        "research_evidence_bundles",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_evidence_bundles_conversation_id",
        table_name="research_evidence_bundles",
    )
    op.drop_table("research_evidence_bundles")
    op.drop_table("research_conversations")
