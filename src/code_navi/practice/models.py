"""ORM models for the unified practice-set gateway (contract §1.1).

Three tables archive generated practice sets, their items and code-fill grading
facts.  ``judge_secret`` keeps everything a judge needs (blank answers, reference
code, quiz-answer references) server-side; every read path must strip it.
All tables carry a nullable ``owner_principal_id`` (compat period) plus
``created_at``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid4())


class PracticeSetModel(Base):
    """One archived generation result of ``POST /api/v1/practice/sets/generate``."""

    __tablename__ = "practice_sets"

    set_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Snapshot of the generation request (topic/context/upload_ids/...) plus the
    # derived fields (coverage, audit, effective_context/effective_topic) so
    # ``GET /practice/sets/{set_id}`` can rebuild the §1.2 response.
    context_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    local_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    generation_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_principal_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)

    items: Mapped[list[PracticeSetItemModel]] = relationship(
        "PracticeSetItemModel",
        back_populates="practice_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PracticeSetItemModel.position",
    )


class PracticeSetItemModel(Base):
    """One PracticeItem archived inside a set.

    ``payload`` never contains grading material: concept answers and code-fill
    blank answers live in ``judge_secret`` only.  ``item_id`` is unique within a
    set (mixed sets reuse the quiz question id), hence the composite PK.
    """

    __tablename__ = "practice_set_items"

    set_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("practice_sets.set_id", ondelete="CASCADE"),
        primary_key=True,
    )
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    item_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Secret store. Structures it must hold:
    # - concept_quiz_question: {"answers": [...], "analysis": str} during S1,
    #   later {"quiz_session_ref": set_id} once P1-A double-writes the quiz archive.
    # - code_fill: {"blanks": [{"blank_id", "answer", "alternate_answers"}],
    #   "reference_code": str}
    judge_secret: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner_principal_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)

    practice_set: Mapped[PracticeSetModel] = relationship(
        "PracticeSetModel", back_populates="items"
    )


class CodeFillAttemptModel(Base):
    """Grading fact for one code-fill submission.

    The composite PK ``(attempt_id, item_id)`` realizes the contract's
    ``UNIQUE(attempt_id, item_id)`` idempotency requirement.
    """

    __tablename__ = "code_fill_attempts"

    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    set_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("practice_sets.set_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    blank_answers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    graded_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    graded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_principal_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


class CodeUploadAnalysisModel(Base):
    """Archived result of ``POST /api/v1/practice/code-uploads/analyze``.

    The original file content is never stored — only its SHA-256 hash and the
    rules-derived structural summary. ``upload_id`` is the opaque reference
    accepted by ``POST /api/v1/practice/sets/generate`` (§1.2) and
    ``POST /api/v1/practice/code-fill/explain-symbol`` (§1.6).
    """

    __tablename__ = "practice_code_uploads"

    upload_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    symbols: Mapped[list | None] = mapped_column(JSON, nullable=True)
    imports: Mapped[list | None] = mapped_column(JSON, nullable=True)
    framework_hints: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    owner_principal_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
