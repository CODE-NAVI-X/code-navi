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
    context_provenance = Column(JSON, nullable=True)
    context_summary_data = Column(JSON, nullable=True)
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


class ResearchReproductionPipelineModel(Base):
    """A persisted rules-only Pipeline for one explicit local paper selection."""

    __tablename__ = "research_reproduction_pipelines"

    id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    pipeline_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchPaperDraftModel(Base):
    __tablename__ = "research_paper_drafts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False, index=True)
    draft_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchPaperReviewModel(Base):
    __tablename__ = "research_paper_reviews"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    review_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchPaperRevisionModel(Base):
    __tablename__ = "research_paper_revisions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_draft_id = Column(String(36), nullable=False, index=True)
    review_id = Column(String(36), nullable=False, index=True)
    revision_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchRevisionSuggestionModel(Base):
    """Persisted candidate text awaiting an explicit user decision."""

    __tablename__ = "research_revision_suggestions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id = Column(String(36), nullable=False, index=True)
    review_id = Column(String(36), nullable=False, index=True)
    revision_task_id = Column(String(36), nullable=False, index=True)
    suggestion_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchSelectedCitationModel(Base):
    """User-selected citation placeholders; original paper text remains untouched."""

    __tablename__ = "research_selected_citations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False, index=True)
    selection_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchCitationQualityCheckModel(Base):
    """Persisted offline checks over one conversation's selected citations."""

    __tablename__ = "research_citation_quality_checks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False, index=True)
    check_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchReproductionEvaluationModel(Base):
    """Persisted, user-triggered reproduction evaluation snapshot."""

    __tablename__ = "research_reproduction_evaluations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False, index=True)
    evaluation_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchReproductionImprovementTaskModel(Base):
    """User-controlled improvement task generated from one evaluation dimension."""

    __tablename__ = "research_reproduction_improvement_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    evaluation_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    task_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ResearchSubmissionReadinessModel(Base):
    __tablename__ = "research_submission_readiness_checks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    check_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class ResearchSubmissionProfileModel(Base):
    """One user-configured local submission profile per research conversation."""

    __tablename__ = "research_submission_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False, unique=True, index=True)
    profile_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
