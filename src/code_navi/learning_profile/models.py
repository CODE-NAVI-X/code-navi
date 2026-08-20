"""SQLAlchemy ORM models backing the learning portrait.

``QuizAttemptModel`` persists every graded answer (single / fill_blank /
short_answer) at grading time.  ``ConfusionMarkModel`` stores the binary
"看不懂/懂了" self-reports attached to learning surfaces (PPT pages, term
explanations, quiz questions).

Both tables carry a nullable ``user_id`` reserved for the future account phase
and use ``profile_id`` (== the practice ``learner_id`` UUID) as the
cross-session aggregation key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from code_navi.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class QuizAttemptModel(Base):
    __tablename__ = "quiz_attempts"

    # Indexes mirror the published learning_profile_v1 migration exactly — the
    # unique (attempt_id, question_id) pair is the retry idempotency key, the
    # (profile_id, ...) index serves the cross-session portrait aggregation.
    __table_args__ = (
        Index("ux_quiz_attempts_idem", "attempt_id", "question_id", unique=True),
        Index("ix_quiz_attempts_profile", "profile_id", "knowledge_point", "created_at"),
        Index("ix_quiz_attempts_session", "session_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    # Client-minted idempotency key; UNIQUE(attempt_id, question_id) protects
    # against double-insert on network retry.
    attempt_id = Column(String(36), nullable=False, index=False)
    quiz_id = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=False, index=False)
    knowledge_point = Column(String(512), nullable=False)
    profile_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True)
    question_id = Column(String(64), nullable=False)
    question_type = Column(String(16), nullable=False)
    points = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    max_score = Column(Integer, nullable=False)
    correct = Column(Boolean, nullable=False)
    graded = Column(Boolean, nullable=False)
    graded_by = Column(String(16), nullable=False)
    is_mock = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)


class ConfusionMarkModel(Base):
    __tablename__ = "confusion_marks"

    # Mirrors the published learning_profile_v1 migration: the unique
    # (session_id, source_type, source_ref) triple is the in-session binary
    # toggle key; the (profile_id, ...) index serves the portrait aggregation.
    __table_args__ = (
        Index(
            "ux_confusion_marks_toggle",
            "session_id",
            "source_type",
            "source_ref",
            unique=True,
        ),
        Index("ix_confusion_marks_profile", "profile_id", "knowledge_point", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(64), nullable=False, index=False)
    profile_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True)
    knowledge_point = Column(String(512), nullable=False)
    source_type = Column(String(16), nullable=False)
    source_ref = Column(String(256), nullable=False)
    # Human-readable content of the mark (term text, slide page, question
    # stem). Nullable so pre-v2 rows survive; the service reads ``label or
    # source_ref`` so nothing displays blank.
    label = Column(String(512), nullable=True)
    # status: "confused" | "understood"
    status = Column(String(16), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
