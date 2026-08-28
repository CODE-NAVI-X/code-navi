"""Add note column to class_members table.

Revision ID: 0021_classroom_member_note
Revises: 0020_classroom
Create Date: 2026-08-28 15:46:00
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0021_classroom_member_note"
down_revision = "0020_classroom"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("class_members", sa.Column("note", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("class_members", "note")
