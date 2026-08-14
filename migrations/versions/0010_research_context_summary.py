"""Add reusable research conversation context summaries.

Revision ID: research_context_summary_v1
Revises: research_context_provenance_repair_v1
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_context_summary_v1"
down_revision: str | None = "research_context_provenance_repair_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research_conversations") as batch:
        batch.add_column(sa.Column("context_summary_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("research_conversations") as batch:
        batch.drop_column("context_summary_data")
