"""Persist user-submitted experiment evidence bundles.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_experiment_evidence_bundles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("bundle_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_research_experiment_evidence_bundles_conversation_id",
        "research_experiment_evidence_bundles",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_experiment_evidence_bundles_conversation_id",
        table_name="research_experiment_evidence_bundles",
    )
    op.drop_table("research_experiment_evidence_bundles")
