"""SQLite persistence model for application-owned research sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, String

from code_navi.learning.models import Base


class ResearchSessionModel(Base):
    """Five-field state and user turn history, stored outside kernel Events."""

    __tablename__ = "research_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    state_data = Column(JSON, nullable=False, default=dict)
    turns_data = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
