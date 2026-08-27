"""Add csrf_token column to auth_sessions and create learning_records table.

Revision ID: auth_csrf_learning_records_v1
Revises: auth_identity_system_v1
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "auth_csrf_learning_records_v1"
down_revision: str | None = "auth_identity_system_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update auth_sessions table: replace csrf_token_hash with plaintext csrf_token
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("csrf_token", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.drop_column("csrf_token_hash")

    # 2. Create learning_records table for shared compiler learning record persistence
    op.create_table(
        "learning_records",
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
        sa.Column("learner_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_line", sa.Integer(), nullable=True),
        sa.Column("ai_status", sa.String(length=32), nullable=False),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("suggestions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reference_score", sa.Integer(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_bytes", sa.Integer(), nullable=False),
        sa.Column("wall_time_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index(
        "ix_learning_records_owner_created_at",
        "learning_records",
        ["owner_principal_id", "created_at"],
    )
    op.create_index(
        "ix_learning_records_learner_created_at",
        "learning_records",
        ["learner_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_records_learner_created_at", table_name="learning_records")
    op.drop_index("ix_learning_records_owner_created_at", table_name="learning_records")
    op.drop_table("learning_records")

    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("csrf_token_hash", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.drop_column("csrf_token")
