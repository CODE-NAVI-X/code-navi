"""Add research orchestrator state, versioned learner profiles, and paper selection tables.

Revision ID: 0025_research_orchestrator_state_v1
Revises: research_artifacts_and_practice_heads_v1
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_research_orchestrator_state_v1"
down_revision: str | Sequence[str] | None = "research_artifacts_and_practice_heads_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_orchestrator_states",
        sa.Column("conversation_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "current_stage",
            sa.String(length=32),
            nullable=False,
            server_default="research_need",
        ),
        sa.Column("completed_stages", sa.JSON(), nullable=False),
        sa.Column("subtasks", sa.JSON(), nullable=False),
        sa.Column("direction_history", sa.JSON(), nullable=False),
        sa.Column("current_plan", sa.JSON(), nullable=True),
        sa.Column("plan_history", sa.JSON(), nullable=False),
        sa.Column("learning_context", sa.JSON(), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("last_failed_user_message", sa.String(length=8000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
    )
    with op.batch_alter_table("research_orchestrator_states", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_orchestrator_states_owner_principal_id"),
            ["owner_principal_id"],
            unique=False,
        )

    op.create_table(
        "research_learner_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
    )
    with op.batch_alter_table("research_learner_profiles", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_learner_profiles_conversation_id"),
            ["conversation_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_learner_profiles_owner_principal_id"),
            ["owner_principal_id"],
            unique=False,
        )

    op.create_table(
        "research_orchestrator_papers",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("paper_url", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="replace"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=True),
    )
    with op.batch_alter_table("research_orchestrator_papers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_research_orchestrator_papers_conversation_id"),
            ["conversation_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_research_orchestrator_papers_owner_principal_id"),
            ["owner_principal_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("research_orchestrator_papers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_orchestrator_papers_owner_principal_id"))
        batch_op.drop_index(batch_op.f("ix_research_orchestrator_papers_conversation_id"))
    op.drop_table("research_orchestrator_papers")

    with op.batch_alter_table("research_learner_profiles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_learner_profiles_owner_principal_id"))
        batch_op.drop_index(batch_op.f("ix_research_learner_profiles_conversation_id"))
    op.drop_table("research_learner_profiles")

    with op.batch_alter_table("research_orchestrator_states", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_research_orchestrator_states_owner_principal_id"))
    op.drop_table("research_orchestrator_states")
