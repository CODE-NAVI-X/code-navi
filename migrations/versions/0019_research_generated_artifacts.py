"""Persist last successful LLM research artefacts per conversation.

Revision ID: research_generated_artifacts_v1
Revises: auth_csrf_learning_records_v1
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "research_generated_artifacts_v1"
down_revision: str | None = "auth_csrf_learning_records_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research_conversations") as batch:
        batch.add_column(sa.Column("generated_artifacts", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("research_conversations") as batch:
        batch.drop_column("generated_artifacts")
