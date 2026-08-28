"""Add classes and class_members tables.

Revision ID: 0020_classroom
Revises: 0019_user_role
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_classroom"
down_revision: str | None = "0019_user_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("invite_code", sa.String(length=12), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_index("ix_classes_invite_code", "classes", ["invite_code"], unique=True)
    op.create_index("ix_classes_owner_user_id", "classes", ["owner_user_id"], unique=False)

    op.create_table(
        "class_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_in_class", sa.String(length=16), server_default="student", nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_id", "user_id", name="uq_class_members_class_user"),
    )
    op.create_index("ix_class_members_class_id", "class_members", ["class_id"], unique=False)
    op.create_index("ix_class_members_user_id", "class_members", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_class_members_user_id", table_name="class_members")
    op.drop_index("ix_class_members_class_id", table_name="class_members")
    op.drop_table("class_members")
    op.drop_index("ix_classes_owner_user_id", table_name="classes")
    op.drop_index("ix_classes_invite_code", table_name="classes")
    op.drop_table("classes")
