"""Baseline schema as previously created by Base.metadata.create_all

Revision ID: 0001
Revises:
Create Date: 2026-07-30

Existing PoC databases were created by ``create_all`` and have no alembic
version table.  Mark them as already at this revision instead of re-running it::

    alembic stamp 0001
    alembic upgrade head
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notebook_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("knowledge_id", sa.String(length=64), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "research_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column("turns_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("research_sessions")
    op.drop_table("notebook_items")
