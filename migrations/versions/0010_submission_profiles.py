"""Persist user-configured local submission requirements.

Revision ID: research_submission_profile_v1
Revises: cli_conversations_v1
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_submission_profile_v1"
down_revision: str | None = "cli_conversations_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_submission_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index(
        "ix_research_submission_profiles_conversation_id",
        "research_submission_profiles",
        ["conversation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_submission_profiles_conversation_id",
        table_name="research_submission_profiles",
    )
    op.drop_table("research_submission_profiles")
