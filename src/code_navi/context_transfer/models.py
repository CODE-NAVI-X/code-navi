"""Shared persistence model for cross-module context handoffs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, String, Text

from code_navi.db import Base


class ContextTransferModel(Base):
    """A restorable context snapshot awaiting confirmation in a target module."""

    __tablename__ = "context_transfers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_module = Column(String(32), nullable=False)
    source_object_type = Column(String(64), nullable=False)
    source_object_id = Column(String(36), nullable=False, index=True)
    source_scope_id = Column(String(64), nullable=False, index=True)
    target_module = Column(String(32), nullable=False)
    topic = Column(String(512), nullable=False)
    summary = Column(Text, nullable=False)
    selected_content = Column(JSON, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="draft", server_default="draft")
    confirmed_conversation_id = Column(String(36), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
