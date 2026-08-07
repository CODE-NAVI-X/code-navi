"""Link confirmed context transfers to Research conversations

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "context_transfers",
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
    )
    op.add_column(
        "context_transfers",
        sa.Column("confirmed_conversation_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "context_transfers",
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "research_conversations",
        sa.Column("context_provenance", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_conversations", "context_provenance")
    op.drop_column("context_transfers", "confirmed_at")
    op.drop_column("context_transfers", "confirmed_conversation_id")
    op.drop_column("context_transfers", "status")
