"""Add project-scoped CLI shell conversations.

Revision ID: cli_conversations_v1
Revises: research_context_summary_v1
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cli_conversations_v1"
down_revision: str | None = "research_context_summary_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cli_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_scope", sa.String(length=2000), nullable=False),
        sa.Column("messages_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cli_conversations_project_scope"),
        "cli_conversations",
        ["project_scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cli_conversations_project_scope"), table_name="cli_conversations")
    op.drop_table("cli_conversations")
