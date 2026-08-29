"""Add practice_sets, practice_set_items and code_fill_attempts tables.

Revision ID: 0022_practice_sets_v1
Revises: 0021_classroom_member_note
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_practice_sets_v1"
down_revision: str | None = "0021_classroom_member_note"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_sets",
        sa.Column("set_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=True),
        sa.Column("local_profile_id", sa.String(length=36), nullable=True),
        sa.Column("profile_id", sa.String(length=36), nullable=True),
        sa.Column("generation_mode", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("set_id"),
    )
    op.create_index(
        "ix_practice_sets_owner_principal_id",
        "practice_sets",
        ["owner_principal_id"],
        unique=False,
    )

    op.create_table(
        "practice_set_items",
        sa.Column("set_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item_kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("judge_secret", sa.JSON(), nullable=True),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["set_id"], ["practice_sets.set_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("set_id", "item_id"),
    )
    op.create_index(
        "ix_practice_set_items_owner_principal_id",
        "practice_set_items",
        ["owner_principal_id"],
        unique=False,
    )

    op.create_table(
        "code_fill_attempts",
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("set_id", sa.String(length=36), nullable=False),
        sa.Column("blank_answers", sa.JSON(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("max_score", sa.Integer(), nullable=True),
        sa.Column("graded_by", sa.String(length=16), nullable=True),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("graded", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["set_id"], ["practice_sets.set_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("attempt_id", "item_id"),
    )
    op.create_index(
        "ix_code_fill_attempts_set_id",
        "code_fill_attempts",
        ["set_id"],
        unique=False,
    )
    op.create_index(
        "ix_code_fill_attempts_owner_principal_id",
        "code_fill_attempts",
        ["owner_principal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_code_fill_attempts_owner_principal_id", table_name="code_fill_attempts"
    )
    op.drop_index("ix_code_fill_attempts_set_id", table_name="code_fill_attempts")
    op.drop_table("code_fill_attempts")
    op.drop_index(
        "ix_practice_set_items_owner_principal_id", table_name="practice_set_items"
    )
    op.drop_table("practice_set_items")
    op.drop_index(
        "ix_practice_sets_owner_principal_id", table_name="practice_sets"
    )
    op.drop_table("practice_sets")
