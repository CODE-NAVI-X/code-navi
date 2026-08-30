"""Add practice_code_uploads table for §1.5 upload analysis archives.

Revision ID: 0023_practice_code_uploads
Revises: 0022_practice_sets_v1
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_practice_code_uploads"
down_revision: str | None = "0022_practice_sets_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_code_uploads",
        sa.Column("upload_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=True),
        sa.Column("imports", sa.JSON(), nullable=True),
        sa.Column("framework_hints", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("upload_id"),
    )
    op.create_index(
        "ix_practice_code_uploads_owner_principal_id",
        "practice_code_uploads",
        ["owner_principal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_practice_code_uploads_owner_principal_id",
        table_name="practice_code_uploads",
    )
    op.drop_table("practice_code_uploads")
