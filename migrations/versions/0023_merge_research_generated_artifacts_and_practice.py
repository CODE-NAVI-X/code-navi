"""Merge research generated-artifacts and practice migration heads.

Revision ID: merge_research_artifacts_practice_v1
Revises: research_generated_artifacts_v1, 0022_practice_sets_v1
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "merge_research_artifacts_practice_v1"
down_revision: tuple[str, str] = (
    "research_generated_artifacts_v1",
    "0022_practice_sets_v1",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
