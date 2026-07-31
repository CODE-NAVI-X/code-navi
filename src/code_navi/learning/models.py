"""SQLAlchemy 2.0 ORM models for the learning module.

``NotebookItemModel`` records every explanation result so students can review
past answers.  The schema is intentionally minimal — extra metadata goes into
the JSON ``extra_data`` column so the table surface stays stable across feature
iterations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, String, Text

from code_navi.db import Base


class NotebookItemModel(Base):
    __tablename__ = "notebook_items"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(String(64), nullable=False)
    knowledge_id = Column(String(64), nullable=False)
    item_type = Column(
        String(32),
        nullable=False,
        comment="One of: summary, note, wrong_answer",
    )
    content = Column(Text, nullable=False)
    extra_data = Column(
        JSON,
        nullable=True,
        comment="Arbitrary payload — e.g. citations, timestamps, error analysis",
    )
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
    )