"""Learning profile v2: confusion_marks.label (human-readable mark content).

Revision ID: learning_profile_v2
Revises: learning_profile_v1
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "learning_profile_v2"
down_revision: str | None = "learning_profile_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Human-readable content of a 不懂 mark (term text, slide page, question
    # stem) so the portrait can show *what* was marked per surface, not just a
    # count. Nullable so pre-v2 rows are preserved; the backfill below makes
    # them display their source_ref instead of a blank slot.
    op.add_column(
        "confusion_marks",
        sa.Column("label", sa.String(length=512), nullable=True),
    )
    op.execute(
        "UPDATE confusion_marks SET label = source_ref WHERE label IS NULL"
    )


def downgrade() -> None:
    op.drop_column("confusion_marks", "label")
