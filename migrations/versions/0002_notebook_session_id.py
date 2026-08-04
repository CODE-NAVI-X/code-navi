"""Scope notebook items by session_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-30

Before this revision ``GET /api/v1/learning/notebook`` ignored its session_id
argument and returned every entry for the PoC user.  Pre-existing rows have no
real session, so they are backfilled into a single legacy bucket rather than
being silently attributed to whichever session reads them first.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_SESSION_ID = "sess-legacy-import"


def upgrade() -> None:
    # server_default backfills existing rows so the NOT NULL constraint holds;
    # it is dropped afterwards so new rows must supply a real session id.
    with op.batch_alter_table("notebook_items") as batch:
        batch.add_column(
            sa.Column(
                "session_id",
                sa.String(length=64),
                nullable=False,
                server_default=_LEGACY_SESSION_ID,
                comment="Client-owned learning session; scopes notebook reads",
            )
        )
    with op.batch_alter_table("notebook_items") as batch:
        batch.alter_column("session_id", server_default=None)
    op.create_index(
        "ix_notebook_items_session_id", "notebook_items", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_notebook_items_session_id", table_name="notebook_items")
    with op.batch_alter_table("notebook_items") as batch:
        batch.drop_column("session_id")
