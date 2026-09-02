"""Add bounded project uploads for practice navigation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0026_practice_code_projects"
down_revision: str | Sequence[str] | None = "0025_research_orchestrator_state_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "practice_code_projects",
        sa.Column("project_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("owner_principal_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_practice_code_projects_owner_principal_id", "practice_code_projects", ["owner_principal_id"])


def downgrade() -> None:
    op.drop_index("ix_practice_code_projects_owner_principal_id", table_name="practice_code_projects")
    op.drop_table("practice_code_projects")
