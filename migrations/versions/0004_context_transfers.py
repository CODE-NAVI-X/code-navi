"""Persist cross-module context transfer drafts

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
        "context_transfers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_module", sa.String(length=32), nullable=False),
        sa.Column("source_object_type", sa.String(length=64), nullable=False),
        sa.Column("source_object_id", sa.String(length=36), nullable=False),
        sa.Column("source_scope_id", sa.String(length=64), nullable=False),
        sa.Column("target_module", sa.String(length=32), nullable=False),
        sa.Column("topic", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("selected_content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_context_transfers_source_object_id",
        "context_transfers",
        ["source_object_id"],
    )
    op.create_index(
        "ix_context_transfers_source_scope_id",
        "context_transfers",
        ["source_scope_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_context_transfers_source_scope_id",
        table_name="context_transfers",
    )
    op.drop_index(
        "ix_context_transfers_source_object_id",
        table_name="context_transfers",
    )
    op.drop_table("context_transfers")
