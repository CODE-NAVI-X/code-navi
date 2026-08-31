"""Merge research generated artifacts and practice migration heads.

Revision ID: research_artifacts_and_practice_heads_v1
Revises: research_generated_artifacts_v1, 0023_practice_code_uploads
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "research_artifacts_and_practice_heads_v1"
down_revision: tuple[str, str] = (
    "research_generated_artifacts_v1",
    "0023_practice_code_uploads",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
