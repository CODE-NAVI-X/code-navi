"""Pure-rule research guidance: stage briefing and study recommendations.

Contract §2.1/§2.2. Both projections read already persisted conversation state,
never call a model and never touch the network. Persisted JSON written by the
validated confirm/pipeline flows is read defensively so the projection stays a
pure reader (write paths own schema validation).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from code_navi.research.conversation_guidance_schemas import (
    StageBriefingEvidenceTrend,
    StageBriefingKnowledgePoint,
    StageBriefingReproductionEntry,
    StageBriefingResponse,
    StageBriefingSummary,
    StudyRecommendation,
    StudyRecommendationAction,
    StudyRecommendationRequest,
    StudyRecommendationsResponse,
)
from code_navi.research.conversation_plan import build_conversation_research_plan
from code_navi.research.conversation_schemas import (
    EvidenceReference,
    ResearchProfile,
)
from code_navi.research.conversation_service import (
    ConversationNotFoundError,
    assess_readiness,
)
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchEvidenceBundleModel,
    ResearchReproductionPipelineModel,
)

_MAX_TRENDS = 3
_MAX_REFS_PER_TREND = 5
_MAX_RECOMMENDATIONS = 6
_MAX_KEYWORD_LENGTH = 128

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_PHRASE_SPLIT_PATTERN = re.compile(r"[,，、;；。/／|\n]+")
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "for",
        "to",
        "in",
        "on",
        "with",
        "from",
        "by",
        "at",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "we",
        "our",
        "their",
        "via",
        "using",
        "based",
        "between",
        "into",
        "over",
        "under",
        "can",
        "may",
        "will",
        "not",
        "but",
        "new",
        "all",
        "you",
        "your",
        "how",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "why",
        "than",
        "then",
        "them",
        "they",
        "some",
        "such",
        "only",
        "more",
        "most",
    }
)


class StudyRecommendationsNotConfirmedError(Exception):
    """Raised when study recommendations are requested without explicit confirmation."""


def _bounded(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


def _provenance_dict(context_provenance: object) -> dict[str, object] | None:
    """Return the stored confirmed-context snapshot when it is a readable mapping."""
    if isinstance(context_provenance, dict) and context_provenance:
        return context_provenance
    return None


def _mastery_snapshot(context_provenance: object) -> dict[str, object] | None:
    """Read the optional §3.2 ``learning_mastery_snapshot`` block if it exists."""
    provenance = _provenance_dict(context_provenance)
    if provenance is None:
        return None
    mastery = provenance.get("learning_mastery_snapshot")
    if isinstance(mastery, dict):
        return mastery
    return None


def _mastery_sets(mastery: dict[str, object] | None) -> tuple[set[str], set[str]]:
    if mastery is None:
        return frozenset(), frozenset()
    strong = {
        value.casefold() for value in mastery.get("strong", []) if isinstance(value, str)
    }
    weak = {value.casefold() for value in mastery.get("weak", []) if isinstance(value, str)}
    return strong, weak


def _snapshot_text(provenance: dict[str, object] | None, key: str, limit: int) -> str | None:
    if provenance is None:
        return None
    value = provenance.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return _bounded(value, limit)


def _knowledge_points(
    mastery: dict[str, object] | None,
) -> list[StageBriefingKnowledgePoint] | None:
    """Project snapshot strong/weak lists; numeric mastery stays unset, never invented."""
    if mastery is None:
        return None
    points: list[StageBriefingKnowledgePoint] = []
    for group in ("strong", "weak"):
        for value in mastery.get(group, []):
            if not isinstance(value, str) or not value.strip():
                continue
            if any(point.name == value for point in points):
                continue
            points.append(StageBriefingKnowledgePoint(name=value, mastery=None))
            if len(points) >= 8:
                return points
    return points


def _pipeline_status(pipeline_data: object) -> str:
    """Project task statuses: any linked evidence wins, otherwise not started."""
    tasks = pipeline_data.get("tasks", []) if isinstance(pipeline_data, dict) else []
    for task in tasks:
        if isinstance(task, dict) and task.get("status") == "evidence_linked":
            return "evidence_linked"
    return "not_started"


def _paper_references(
    bundle_id: str,
    papers: list[object],
    seen_urls: set[str],
) -> list[EvidenceReference]:
    """Normalize stored papers into deduplicated evidence references."""
    references: list[EvidenceReference] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        url = paper.get("url")
        title = paper.get("title")
        source_name = paper.get("source_name")
        if not isinstance(url, str) or not url or url.casefold() in seen_urls:
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(source_name, str) or not source_name.strip():
            continue
        seen_urls.add(url.casefold())
        abstract = paper.get("abstract_excerpt")
        has_abstract = isinstance(abstract, str) and bool(abstract.strip())
        year = paper.get("year")
        references.append(
            EvidenceReference(
                bundle_id=bundle_id,
                paper_url=url,
                title=_bounded(title, 1000),
                source_name=_bounded(source_name, 200),
                year=year if isinstance(year, int) else None,
                evidence_level="abstract" if has_abstract else "metadata",
                evidence_summary=_bounded(abstract, 1000) if has_abstract else None,
            )
        )
    return references


def _trend_keyword_counts(titles: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for title in titles:
        for keyword in {
            token for token in _TOKEN_PATTERN.findall(title.casefold()) if len(token) >= 3
        }:
            if keyword not in _STOPWORDS:
                counts[keyword] = counts.get(keyword, 0) + 1
    return counts


class ResearchConversationGuidanceService:
    """Rule-only guidance projections scoped to one research conversation."""

    def stage_briefing(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
        include_evidence_trends: bool = False,
    ) -> StageBriefingResponse:
        conversation = self._get_conversation(conversation_id, db, owned_ids=owned_ids)
        provenance = _provenance_dict(conversation.context_provenance)
        mastery = _mastery_snapshot(conversation.context_provenance)

        summary = StageBriefingSummary(
            topic=_snapshot_text(provenance, "topic", 500),
            digest=_snapshot_text(provenance, "summary", 1000),
            knowledge_points=_knowledge_points(mastery),
        )

        bundle_rows = (
            db.query(ResearchEvidenceBundleModel)
            .filter(ResearchEvidenceBundleModel.conversation_id == conversation.id)
            .order_by(ResearchEvidenceBundleModel.created_at, ResearchEvidenceBundleModel.id)
            .all()
        )
        latest_pipeline = (
            db.query(ResearchReproductionPipelineModel)
            .filter(ResearchReproductionPipelineModel.conversation_id == conversation.id)
            .order_by(
                ResearchReproductionPipelineModel.created_at.desc(),
                ResearchReproductionPipelineModel.id.desc(),
            )
            .first()
        )

        evidence_trends: list[StageBriefingEvidenceTrend] = []
        if include_evidence_trends:
            evidence_trends = self._evidence_trends(bundle_rows)

        return StageBriefingResponse(
            conversation_id=conversation.id,
            has_learning_context=provenance is not None,
            stage_summary=summary,
            reproduction_entry=StageBriefingReproductionEntry(
                bundle_count=len(bundle_rows),
                pipeline_status=(
                    _pipeline_status(latest_pipeline.pipeline_data)
                    if latest_pipeline is not None
                    else None
                ),
            ),
            evidence_trends=evidence_trends,
            generated_at=datetime.now(UTC),
        )

    def _evidence_trends(
        self,
        bundle_rows: list[ResearchEvidenceBundleModel],
    ) -> list[StageBriefingEvidenceTrend]:
        seen_urls: set[str] = set()
        references: list[EvidenceReference] = []
        for bundle in bundle_rows:
            papers = (
                bundle.bundle_data.get("papers", []) if isinstance(bundle.bundle_data, dict) else []
            )
            references.extend(_paper_references(bundle.id, papers, seen_urls))
        if not references:
            return []

        entries = [
            (reference, set(_trend_keyword_counts([reference.title])))
            for reference in references
        ]
        counts: dict[str, int] = {}
        for _, keywords in entries:
            for keyword in keywords:
                counts[keyword] = counts.get(keyword, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:_MAX_TRENDS]

        trends: list[StageBriefingEvidenceTrend] = []
        for keyword, paper_count in ranked:
            matched = [
                reference for reference, keywords in entries if keyword in keywords
            ]
            trends.append(
                StageBriefingEvidenceTrend(
                    keyword=keyword,
                    paper_count=paper_count,
                    evidence_refs=matched[:_MAX_REFS_PER_TREND],
                )
            )
        return trends

    def study_recommendations(
        self,
        conversation_id: str,
        request: StudyRecommendationRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> StudyRecommendationsResponse:
        conversation = self._get_conversation(conversation_id, db, owned_ids=owned_ids)
        if not request.user_confirmed:
            raise StudyRecommendationsNotConfirmedError()

        profile = ResearchProfile.model_validate(conversation.profile_data)
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.stage == "ready_for_plan"
        )
        strong, weak = _mastery_sets(_mastery_snapshot(conversation.context_provenance))

        candidates: list[tuple[str, str]] = []
        for method in profile.methods:
            reason = f"来自已确认的研究方法“{_bounded(method, 120)}”。"
            candidates.extend((phrase, reason) for phrase in _split_phrases(method))
        if profile.data_requirements:
            reason = f"来自已确认的数据需求“{_bounded(profile.data_requirements, 150)}”。"
            phrases = _split_phrases(profile.data_requirements)
            candidates.extend((phrase, reason) for phrase in phrases)
        if plan is not None:
            for entry in plan.suggested_datasets_or_metrics:
                reason = f"来自研究计划的数据与指标建议“{_bounded(entry.content, 150)}”。"
                candidates.extend((phrase, reason) for phrase in _split_phrases(entry.content))

        recommendations: list[StudyRecommendation] = []
        seen: set[str] = set()
        for phrase, reason in candidates:
            key = phrase.casefold()
            if key in seen:
                continue
            seen.add(key)
            if strong and key in strong:
                mastery_status = "mastered"
            elif weak and key in weak:
                mastery_status = "weak"
            else:
                mastery_status = "unknown"
            if mastery_status == "mastered":
                action = StudyRecommendationAction(
                    type="practice_set",
                    payload={"kind": "code_practice", "topic": phrase, "count": 5},
                )
            else:
                action = StudyRecommendationAction(
                    type="learning_explain",
                    payload={"knowledge_point": phrase},
                )
            recommendations.append(
                StudyRecommendation(
                    knowledge_point=phrase,
                    reason=reason,
                    mastery_status=mastery_status,
                    action=action,
                )
            )
            if len(recommendations) >= _MAX_RECOMMENDATIONS:
                break

        return StudyRecommendationsResponse(
            recommendations=recommendations,
            provenance_note=(
                "本建议由已确认科研画像与研究计划按规则提取，未调用模型、未联网；"
                "mastery_status 仅对照学习掌握快照，快照缺失或未命中时为 unknown，不构成模型判断。"
            ),
        )

    @staticmethod
    def _get_conversation(
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ResearchConversationModel:
        conversation = db.get(ResearchConversationModel, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        if (
            owned_ids is not None
            and conversation.owner_principal_id
            and conversation.owner_principal_id not in owned_ids
        ):
            raise ConversationNotFoundError(conversation_id)
        return conversation


def _split_phrases(value: str) -> list[str]:
    """Split profile text on common delimiters into bounded keyword phrases."""
    phrases: list[str] = []
    for part in _PHRASE_SPLIT_PATTERN.split(value):
        cleaned = " ".join(part.split())
        if not cleaned or len(cleaned) > _MAX_KEYWORD_LENGTH:
            continue
        phrases.append(cleaned)
    return phrases


__all__ = [
    "ResearchConversationGuidanceService",
    "StudyRecommendationsNotConfirmedError",
]
