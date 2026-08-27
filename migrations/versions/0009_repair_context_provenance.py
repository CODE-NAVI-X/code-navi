"""Repair a missing conversation provenance column in stale local databases.

Revision ID: research_context_provenance_repair_v1
Revises: research_citation_scaffold_v1
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_context_provenance_repair_v1"
down_revision: str | None = "research_citation_scaffold_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column only when a stale SQLite schema does not already have it."""
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("research_conversations")
    }
    if "context_provenance" not in columns:
        with op.batch_alter_table("research_conversations") as batch:
            batch.add_column(sa.Column("context_provenance", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Keep the column owned by revision 0005 when leaving this repair revision."""
