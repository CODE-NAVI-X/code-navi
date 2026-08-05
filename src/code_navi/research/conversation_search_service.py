"""Explicit academic-search handoff for conversational research profiles."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from code_navi.research.academic import AcademicSearchTool
from code_navi.research_tools import register_research_tools
from kernel.core import (
    PermissionGrant,
    ToolCall,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
)

from .conversation_difficulty import build_paper_analysis
from .conversation_schemas import (
    AnalyzeConversationPaperRequest,
    ConversationEvidenceBundle,
    CreateConversationEvidenceBundleRequest,
    PaperAnalysis,
    ResearchProfile,
    ResearchSearchPlan,
    ResearchSearchSource,
)
from .conversation_service import ConversationNotFoundError, assess_readiness
from .models import ResearchConversationModel, ResearchEvidenceBundleModel
from .research_artifact_llm import (
    ResearchArtifactGenerator,
    RuntimeResearchArtifactGenerator,
)


class ConversationSearchNotReadyError(ValueError):
    """Raised when the current profile is too sparse for a bounded search."""


class ConversationPaperNotFoundError(LookupError):
    """Raised when a user has not selected a paper from saved evidence."""


class ResearchConversationSearchService:
    """Prepare a query without a model and dispatch only after explicit confirmation."""

    def __init__(
        self,
        search_tool: AcademicSearchTool | None = None,
        artifact_generator: ResearchArtifactGenerator | None = None,
    ) -> None:
        self.search_tool = search_tool or AcademicSearchTool()
        self.artifact_generator = artifact_generator or RuntimeResearchArtifactGenerator()

    def plan(self, conversation_id: str, db: Session) -> ResearchSearchPlan:
        """Return a reviewable plan without accessing any network source."""
        profile = self._profile(conversation_id, db)
        if not assess_readiness(profile).can_prepare_search:
            raise ConversationSearchNotReadyError(
                "当前科研画像还不足以生成检索计划，请至少明确研究主题和候选问题。"
            )
        queries = _profile_queries(profile)
        return ResearchSearchPlan(
            conversation_id=conversation_id,
            query=queries[0],
            alternative_queries=queries[1:],
            sources=[
                ResearchSearchSource(
                    id="openalex",
                    display_name="OpenAlex",
                    homepage="https://openalex.org",
                    scope="开放学术图谱中的论文题录、作者、年份、DOI 与可用摘要",
                ),
                ResearchSearchSource(
                    id="crossref",
                    display_name="Crossref",
                    homepage="https://www.crossref.org",
                    scope="出版社注册的 DOI 与期刊论文元数据，以及来源提供的摘要",
                ),
                ResearchSearchSource(
                    id="arxiv",
                    display_name="arXiv",
                    homepage="https://arxiv.org",
                    scope="预印本论文的题录与摘要，不下载或声称已阅读全文",
                ),
            ],
            provenance_note=(
                "检索词仅由当前科研画像中已确认的主题、问题、场景和方法组合生成；"
                "生成计划不会联网，执行前必须由用户确认。"
            ),
        )

    def search(
        self,
        conversation_id: str,
        request: CreateConversationEvidenceBundleRequest,
        db: Session,
    ) -> ConversationEvidenceBundle:
        """Dispatch the allow-listed Tool once after an explicit API request."""
        plan = self.plan(conversation_id, db)
        query = request.query or plan.query
        cached = self._cached_bundle(conversation_id, query, request.sources, db)
        if cached is not None:
            return cached.model_copy(update={"cache_hit": True})
        registry = ToolRegistry()
        register_research_tools(registry, self.search_tool)
        dispatcher = registry.bind(
            PermissionGrant(
                conversation_id,
                frozenset({ToolPermission.READ, ToolPermission.NETWORK}),
            ),
            ToolExecutionContext(conversation_id),
        )
        result = dispatcher.dispatch(
            ToolCall(
                f"academic-search-{conversation_id}",
                "academic_search",
                {"query": query, "sources": request.sources},
            )
        )
        if not result.result["ok"]:
            raise RuntimeError("academic_search Tool did not return an evidence bundle")
        payload = dict(result.result["value"])
        payload.pop("session_id", None)
        record = ResearchEvidenceBundleModel(conversation_id=conversation_id, bundle_data={})
        db.add(record)
        db.flush()
        payload["bundle_id"] = record.id
        payload["conversation_id"] = conversation_id
        payload["requested_sources"] = request.sources
        payload["tool_audit"] = result.result["audit"]
        bundle = ConversationEvidenceBundle.model_validate(payload)
        record.bundle_data = bundle.model_dump(mode="json")
        db.commit()
        return bundle

    def list_bundles(self, conversation_id: str, db: Session) -> list[ConversationEvidenceBundle]:
        """Restore prior evidence without performing another network request."""
        self._profile(conversation_id, db)
        records = (
            db.query(ResearchEvidenceBundleModel)
            .filter(ResearchEvidenceBundleModel.conversation_id == conversation_id)
            .order_by(ResearchEvidenceBundleModel.created_at.desc())
            .all()
        )
        return [ConversationEvidenceBundle.model_validate(record.bundle_data) for record in records]

    def analyze_paper(
        self,
        conversation_id: str,
        request: AnalyzeConversationPaperRequest,
        db: Session,
    ) -> PaperAnalysis:
        """Analyze only a paper the user explicitly selected from saved evidence."""
        for bundle in self.list_bundles(conversation_id, db):
            for paper in bundle.papers:
                if paper.url == request.paper_url:
                    return build_paper_analysis(
                        paper,
                        generator=self.artifact_generator,
                        conversation_id=conversation_id,
                    )
        raise ConversationPaperNotFoundError(request.paper_url)

    def _cached_bundle(
        self,
        conversation_id: str,
        query: str,
        sources: list[str],
        db: Session,
    ) -> ConversationEvidenceBundle | None:
        ttl_seconds = max(0, int(os.getenv("CODE_NAVI_ACADEMIC_CACHE_TTL_SECONDS", "3600")))
        if ttl_seconds == 0:
            return None
        cutoff = datetime.now(UTC) - timedelta(seconds=ttl_seconds)
        records = (
            db.query(ResearchEvidenceBundleModel)
            .filter(ResearchEvidenceBundleModel.conversation_id == conversation_id)
            .order_by(ResearchEvidenceBundleModel.created_at.desc())
            .all()
        )
        expected_sources = list(dict.fromkeys(sources))
        for record in records:
            created_at = record.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if created_at < cutoff:
                break
            bundle = ConversationEvidenceBundle.model_validate(record.bundle_data)
            if (
                " ".join(bundle.query.split()).casefold() == " ".join(query.split()).casefold()
                and bundle.requested_sources == expected_sources
            ):
                return bundle
        return None

    @staticmethod
    def _profile(conversation_id: str, db: Session) -> ResearchProfile:
        conversation = db.get(ResearchConversationModel, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return ResearchProfile.model_validate(conversation.profile_data)


def _profile_queries(profile: ResearchProfile) -> list[str]:
    """Build concise queries from structured fields, never from the raw chat sentence."""
    question = next(iter(profile.research_questions or profile.candidate_questions), None)
    primary_parts = [profile.topic, question, profile.context, *profile.methods[:2]]
    primary = _bounded_query(primary_parts)
    alternatives = [
        _bounded_query([profile.topic, profile.context]),
        _bounded_query([profile.topic, *profile.methods[:2]]),
        _bounded_query([profile.topic, profile.data_requirements]),
    ]
    return list(dict.fromkeys(value for value in [primary, *alternatives] if value))


def _bounded_query(parts: list[str | None]) -> str:
    values = [" ".join(value.split()) for value in parts if value and value.strip()]
    return " ".join(dict.fromkeys(values))[:300]


__all__ = [
    "ConversationPaperNotFoundError",
    "ConversationSearchNotReadyError",
    "ResearchConversationSearchService",
]
