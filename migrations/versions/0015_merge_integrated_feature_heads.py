"""Merge workspace, reproduction, and learning-profile migration heads.

Revision ID: integrated_feature_heads_v1
Revises: persistent_workspace_foundation_v1, reproduction_project_evaluation_v1,
    learning_profile_v2
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "integrated_feature_heads_v1"
down_revision: tuple[str, str, str] = (
    "persistent_workspace_foundation_v1",
    "reproduction_project_evaluation_v1",
    "learning_profile_v2",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
