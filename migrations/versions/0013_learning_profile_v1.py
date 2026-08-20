"""Learning profile: quiz attempts + confusion marks.

Revision ID: learning_profile_v1
Revises: research_citation_quality_v1
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "learning_profile_v1"
down_revision: str | None = "research_citation_quality_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Quiz answers + grades, persisted server-side at grading time.  The
    # ``attempt_id`` is a client-minted idempotency key so a network retry
    # cannot double-insert.  ``profile_id`` (== the practice ``learner_id``
    # UUID) is the cross-session portrait aggregation key; ``user_id`` is
    # reserved for the future account phase and stays NULL for now.
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("quiz_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("knowledge_point", sa.String(length=512), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("question_type", sa.String(length=16), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("graded", sa.Boolean(), nullable=False),
        sa.Column("graded_by", sa.String(length=16), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ux_quiz_attempts_idem",
        "quiz_attempts",
        ["attempt_id", "question_id"],
        unique=True,
    )
    op.create_index(
        "ix_quiz_attempts_profile",
        "quiz_attempts",
        ["profile_id", "knowledge_point", "created_at"],
    )
    op.create_index(
        "ix_quiz_attempts_session",
        "quiz_attempts",
        ["session_id", "created_at"],
    )

    # Self-reported "看不懂/懂了" marks on learning surfaces (PPT pages, term
    # explanations, quiz questions).  ``knowledge_point`` is the semantic,
    # free-text knowledge name so a regenerated PPT or re-made quiz never
    # orphans a mark from the portrait.  ``source_type`` + ``source_ref`` keep
    # traceability to the exact entity.  The unique pair (session_id,
    # source_type, source_ref) is the in-session binary toggle key.
    op.create_table(
        "confusion_marks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("knowledge_point", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ux_confusion_marks_toggle",
        "confusion_marks",
        ["session_id", "source_type", "source_ref"],
        unique=True,
    )
    op.create_index(
        "ix_confusion_marks_profile",
        "confusion_marks",
        ["profile_id", "knowledge_point", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_confusion_marks_profile", table_name="confusion_marks")
    op.drop_index("ux_confusion_marks_toggle", table_name="confusion_marks")
    op.drop_table("confusion_marks")
    op.drop_index("ix_quiz_attempts_session", table_name="quiz_attempts")
    op.drop_index("ix_quiz_attempts_profile", table_name="quiz_attempts")
    op.drop_index("ux_quiz_attempts_idem", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
