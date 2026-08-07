"""SQLite persistence model for application-owned research sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, String

from code_navi.db import Base


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


class ResearchConversationModel(Base):
    """Dynamic research profile and full conversational message history."""

    __tablename__ = "research_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_data = Column(JSON, nullable=False, default=dict)
    messages_data = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ResearchEvidenceBundleModel(Base):
    """Persisted, restorable output from one explicit academic search run."""

    __tablename__ = "research_evidence_bundles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False, index=True)
    bundle_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchExperimentEvidenceBundleModel(Base):
    """User-submitted experiment evidence, stored independently of Kernel Events."""

    __tablename__ = "research_experiment_evidence_bundles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False, index=True)
    bundle_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
