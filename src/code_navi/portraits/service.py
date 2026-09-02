"""Service layer for the unified portraits overview read endpoint (contract §4.1).

This is a pure read-only aggregation projection over existing facts:
- Learning slice delegates to ``ProfileService`` (same aggregation as ``GET /api/v1/profile``).
- Research slice projects conversation records, evidence bundle counts, and pipeline status.
- Bridges slice projects context transfer and study recommendation signals.

Pure rules, no model invocations, no network requests, and no second set of fact tables.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from code_navi.context_transfer.models import ContextTransferModel
from code_navi.learning_profile.service import ProfileService
from code_navi.research.conversation_guidance import (
    ResearchConversationGuidanceService,
    _pipeline_status,
)
from code_navi.research.conversation_guidance_schemas import StudyRecommendationRequest
from code_navi.research.conversation_schemas import ResearchProfile
from code_navi.research.conversation_service import assess_readiness
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchEvidenceBundleModel,
    ResearchReproductionEvaluationModel,
    ResearchReproductionPipelineModel,
)

from .schemas import (
    BridgesPortraitOverview,
    LearningKnowledgeGapOverview,
    LearningMasteryOverview,
    LearningPortraitOverview,
    LearningReviewQueueOverview,
    LearningToResearchBridge,
    PortraitsOverviewResponse,
    ResearchConversationOverview,
    ResearchPortraitOverview,
    ResearchToLearningBridge,
)

_SOURCE_ORDER_MAP = {"ppt_page": 0, "explain": 1, "quiz_question": 2}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


class PortraitsOverviewService:
    """Aggregate learning, research, and cross-module bridge facts into one portrait."""

    def __init__(
        self,
        profile_service: ProfileService | None = None,
        guidance_service: ResearchConversationGuidanceService | None = None,
    ) -> None:
        self._profile_service = profile_service or ProfileService()
        self._guidance_service = guidance_service or ResearchConversationGuidanceService()

    def get_overview(
        self,
        *,
        profile_id: str,
        local_profile_id: str | None = None,
        conversation_limit: int = 5,
        db: Session,
        owned_ids: list[str] | None = None,
    ) -> PortraitsOverviewResponse:
        """Aggregate the unified portrait for one ``profile_id`` or owned principals."""
        learning_overview = self._aggregate_learning(
            profile_id=profile_id,
            local_profile_id=local_profile_id,
            db=db,
            owned_ids=owned_ids,
        )
        research_overview, latest_conv_id = self._aggregate_research(
            conversation_limit=conversation_limit,
            db=db,
            owned_ids=owned_ids,
        )
        bridges_overview = self._aggregate_bridges(
            latest_conv_id=latest_conv_id,
            db=db,
            owned_ids=owned_ids,
        )

        return PortraitsOverviewResponse(
            profile_id=profile_id,
            learning=learning_overview,
            research=research_overview,
            bridges=bridges_overview,
            generated_by="rules",
            generated_at=_iso_now(),
        )

    def _aggregate_learning(
        self,
        *,
        profile_id: str,
        local_profile_id: str | None,
        db: Session,
        owned_ids: list[str] | None,
    ) -> LearningPortraitOverview:
        profile = self._profile_service.get_profile(profile_id, db, owned_ids=owned_ids)

        graded_attempts = sum(m.sample_size for m in profile.mastery)
        strong_points = profile.strengths[:5]
        weak_points = profile.weaknesses[:5]
        insufficient_sample = not any(m.status == "sufficient" for m in profile.mastery)

        active_confusion_marks = sum(c.mark_count for c in profile.confusion)
        surface_counts: dict[str, int] = {}
        for item in profile.confusion:
            for surface_type, marks in item.by_type.items():
                surface_counts[surface_type] = surface_counts.get(surface_type, 0) + len(marks)

        top_surfaces = sorted(
            surface_counts.keys(),
            key=lambda s: (-surface_counts[s], _SOURCE_ORDER_MAP.get(s, 99)),
        )[:3]

        gaps_response = self._profile_service.get_knowledge_gaps(
            local_profile_id=local_profile_id or "",
            profile_id=profile_id,
            db=db,
            owned_ids=owned_ids,
            limit=8,
        )
        knowledge_gaps = [
            LearningKnowledgeGapOverview(
                knowledge_point=item.topic,
                source_type=item.source_type,
                summary=item.summary,
            )
            for item in gaps_response.items[:8]
        ]

        return LearningPortraitOverview(
            mastery=LearningMasteryOverview(
                graded_attempts=graded_attempts,
                strong_points=strong_points,
                weak_points=weak_points,
                insufficient_sample=insufficient_sample,
            ),
            review_queue=LearningReviewQueueOverview(
                active_confusion_marks=active_confusion_marks,
                top_surfaces=top_surfaces,
            ),
            knowledge_gaps=knowledge_gaps,
        )

    def _aggregate_research(
        self,
        *,
        conversation_limit: int,
        db: Session,
        owned_ids: list[str] | None,
    ) -> tuple[ResearchPortraitOverview, str | None]:
        conv_query = db.query(ResearchConversationModel)
        if owned_ids:
            conv_query = conv_query.filter(
                ResearchConversationModel.owner_principal_id.in_(owned_ids)
            )
        else:
            conv_query = conv_query.filter(
                ResearchConversationModel.owner_principal_id.is_(None)
            )

        conv_rows = (
            conv_query.order_by(
                ResearchConversationModel.updated_at.desc(),
                ResearchConversationModel.id.desc(),
            )
            .limit(conversation_limit)
            .all()
        )

        conversations: list[ResearchConversationOverview] = []
        for row in conv_rows:
            bundle_count = (
                db.query(func.count(ResearchEvidenceBundleModel.id))
                .filter(ResearchEvidenceBundleModel.conversation_id == row.id)
                .scalar()
                or 0
            )

            latest_pipeline = (
                db.query(ResearchReproductionPipelineModel)
                .filter(ResearchReproductionPipelineModel.conversation_id == row.id)
                .order_by(
                    ResearchReproductionPipelineModel.created_at.desc(),
                    ResearchReproductionPipelineModel.id.desc(),
                )
                .first()
            )
            pipeline_status = (
                _pipeline_status(latest_pipeline.pipeline_data)
                if latest_pipeline is not None
                else None
            )

            latest_eval = (
                db.query(ResearchReproductionEvaluationModel)
                .filter(ResearchReproductionEvaluationModel.conversation_id == row.id)
                .order_by(
                    ResearchReproductionEvaluationModel.created_at.desc(),
                    ResearchReproductionEvaluationModel.id.desc(),
                )
                .first()
            )

            readiness: str | None = None
            if latest_eval is not None and latest_eval.evaluation_data:
                total_score = latest_eval.evaluation_data.get("total_score")
                if total_score is not None:
                    schema_ver = latest_eval.evaluation_data.get("schema_version")
                    if schema_ver == "reproduction-project-evaluation.v1":
                        readiness = f"{total_score}/100"
                    else:
                        readiness = f"{total_score}/12"
            if readiness is None:
                prof = ResearchProfile.model_validate(row.profile_data or {})
                readiness = assess_readiness(prof).stage

            topic = (row.profile_data or {}).get("topic")

            conversations.append(
                ResearchConversationOverview(
                    conversation_id=row.id,
                    topic=topic,
                    updated_at=row.updated_at.isoformat(),
                    readiness=readiness,
                    evidence_bundle_count=bundle_count,
                    reproduction_pipeline_status=pipeline_status,
                )
            )

        latest_conv_id = conv_rows[0].id if conv_rows else None
        return ResearchPortraitOverview(conversations=conversations), latest_conv_id

    def _aggregate_bridges(
        self,
        *,
        latest_conv_id: str | None,
        db: Session,
        owned_ids: list[str] | None,
    ) -> BridgesPortraitOverview:
        transfer_query = db.query(ContextTransferModel)
        if owned_ids:
            transfer_query = transfer_query.filter(
                ContextTransferModel.owner_principal_id.in_(owned_ids)
            )
        else:
            transfer_query = transfer_query.filter(
                ContextTransferModel.owner_principal_id.is_(None)
            )

        latest_transfer = transfer_query.order_by(
            ContextTransferModel.created_at.desc(),
            ContextTransferModel.id.desc(),
        ).first()

        latest_transfer_id: str | None = None
        confirmed = False
        has_mastery_snapshot = False

        if latest_transfer is not None:
            latest_transfer_id = latest_transfer.id
            confirmed = latest_transfer.status == "confirmed"
            if latest_transfer.confirmed_conversation_id:
                conv = db.get(ResearchConversationModel, latest_transfer.confirmed_conversation_id)
                if conv and isinstance(conv.context_provenance, dict):
                    has_mastery_snapshot = bool(
                        conv.context_provenance.get("learning_mastery_snapshot")
                    )

        pending_recs = 0
        if latest_conv_id is not None:
            try:
                recs_resp = self._guidance_service.study_recommendations(
                    latest_conv_id,
                    StudyRecommendationRequest(user_confirmed=True),
                    db,
                    owned_ids=owned_ids,
                )
                pending_recs = len(recs_resp.recommendations)
            except Exception:
                pending_recs = 0

        return BridgesPortraitOverview(
            learning_to_research=LearningToResearchBridge(
                latest_transfer_id=latest_transfer_id,
                confirmed=confirmed,
                has_mastery_snapshot=has_mastery_snapshot,
            ),
            research_to_learning=ResearchToLearningBridge(
                pending_study_recommendations=pending_recs,
            ),
        )


__all__ = ["PortraitsOverviewService"]
