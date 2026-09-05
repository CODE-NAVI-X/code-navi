"""Explicit academic-search handoff for conversational research profiles."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from code_navi.learning.models import NotebookItemModel
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
from .conversation_plan import build_conversation_research_plan
from .conversation_schemas import (
    AnalyzeConversationPaperRequest,
    ConversationEvidenceBundle,
    CreateConversationEvidenceBundleRequest,
    EvidenceReference,
    PaperAnalysis,
    PaperReadingEvidence,
    PaperReadingSection,
    ResearchProfile,
    ResearchSearchPlan,
    ResearchSearchSource,
    SavedResearchNotebookNote,
    SaveResearchNotebookNoteRequest,
    SelectedResearchPaper,
)
from .conversation_service import ConversationNotFoundError, assess_readiness
from .models import ResearchConversationModel, ResearchEvidenceBundleModel
from .paper_reading import (
    read_public_paper_pdf,
    read_uploaded_pdf_bytes,
)
from .research_artifact_llm import (
    ResearchArtifactGenerator,
    RuntimeResearchArtifactGenerator,
)
from .schemas import AcademicPaperResult


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
        if (request.query or "").strip():
            # Design contract: a user-provided query with explicit confirmation
            # starts the formal search directly. Profile readiness only gates
            # the auto-generated search plan, never the confirmed user query.
            query = request.query or ""
        else:
            query = self.plan(conversation_id, db).query
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
        payload["papers"] = [
            {**paper, "paper_id": _bundle_paper_id(record.id, paper)}
            for paper in payload["papers"]
            if isinstance(paper, dict)
        ]
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
        conversation = self._get_conversation(conversation_id, db)
        for bundle in self.list_bundles(conversation_id, db):
            for paper in bundle.papers:
                if paper.url == request.paper_url:
                    paper_reading, resolved_arxiv_id = self._resolve_paper_reading(
                        paper,
                        paper_pdf_url=request.paper_pdf_url,
                    )
                    return self._save_paper_analysis(
                        conversation_id=conversation_id,
                        conversation=conversation,
                        bundle=bundle,
                        paper=paper,
                        paper_reading=paper_reading,
                        arxiv_id=resolved_arxiv_id,
                        db=db,
                    )
        raise ConversationPaperNotFoundError(request.paper_url)

    def analyze_paper_upload(
        self,
        conversation_id: str,
        *,
        paper_url: str,
        payload: bytes,
        filename: str | None,
        db: Session,
    ) -> PaperAnalysis:
        """Analyze a selected paper using a PDF uploaded in the current request."""
        conversation = self._get_conversation(conversation_id, db)
        for bundle in self.list_bundles(conversation_id, db):
            for paper in bundle.papers:
                if paper.url == paper_url:
                    reading = read_uploaded_pdf_bytes(payload, filename=filename)
                    paper_reading = PaperReadingEvidence(
                        source_url=reading.source_url,
                        page_count=reading.page_count,
                        pages_read=reading.pages_read,
                        text_excerpt=reading.text_excerpt,
                        sections=[
                            PaperReadingSection(
                                key=section.key,
                                title=section.title,
                                order=section.order,
                                text=section.text,
                            )
                            for section in reading.sections
                        ],
                    )
                    return self._save_paper_analysis(
                        conversation_id=conversation_id,
                        conversation=conversation,
                        bundle=bundle,
                        paper=paper,
                        paper_reading=paper_reading,
                        arxiv_id=paper.arxiv_id,
                        db=db,
                    )
        raise ConversationPaperNotFoundError(paper_url)

    def _resolve_paper_reading(
        self,
        paper: AcademicPaperResult,
        *,
        paper_pdf_url: str | None,
    ) -> tuple[PaperReadingEvidence | None, str | None]:
        arxiv_id = paper.arxiv_id
        if not paper_pdf_url and not arxiv_id:
            match = self.search_tool.resolve_arxiv_paper(
                title=paper.title,
                authors=paper.authors,
                year=paper.year,
            )
            arxiv_id = match.identifier if match is not None else None
        if not paper_pdf_url and not arxiv_id:
            return None, None
        reading = read_public_paper_pdf(pdf_url=paper_pdf_url, arxiv_id=arxiv_id)
        return (
            PaperReadingEvidence(
                source_url=reading.source_url,
                page_count=reading.page_count,
                pages_read=reading.pages_read,
                text_excerpt=reading.text_excerpt,
                sections=[
                    PaperReadingSection(
                        key=section.key,
                        title=section.title,
                        order=section.order,
                        text=section.text,
                    )
                    for section in reading.sections
                ],
            ),
            arxiv_id,
        )

    def _save_paper_analysis(
        self,
        *,
        conversation_id: str,
        conversation: ResearchConversationModel,
        bundle: ConversationEvidenceBundle,
        paper: AcademicPaperResult,
        paper_reading: PaperReadingEvidence | None,
        arxiv_id: str | None,
        db: Session,
    ) -> PaperAnalysis:
        profile = ResearchProfile.model_validate(conversation.profile_data)
        question = next(iter(profile.research_questions or profile.candidate_questions), None)
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.can_prepare_search
        )
        analysis = build_paper_analysis(
            paper,
            evidence_ref=_evidence_reference(bundle.bundle_id, paper),
            paper_reading=paper_reading,
            research_context={
                "research_topic": profile.topic,
                "research_question": question,
                "research_motivation": profile.motivation,
                "methods": profile.methods,
                "data_requirements": profile.data_requirements,
                "metrics": profile.metrics,
                "constraints": profile.constraints,
                "time_scope": profile.time_scope,
                "expected_output": profile.expected_output,
                "reproduction_goal": (
                    "围绕选中论文设计可在当前设备与时间约束下执行的最小复现核对路径，"
                    "并明确哪些结论仍需用户实验验证。"
                ),
                "current_plan": (
                    plan.model_dump(mode="json") if plan is not None else None
                ),
            },
            generator=self.artifact_generator,
            conversation_id=conversation_id,
        )
        selected = SelectedResearchPaper(
            bundle_id=bundle.bundle_id,
            title=paper.title,
            url=paper.url,
            authors=paper.authors,
            year=paper.year,
            source_name=paper.source_name,
            doi=paper.doi,
            arxiv_id=arxiv_id,
            abstract_excerpt=paper.abstract_excerpt,
            paper_kind=paper.paper_kind.content if paper.paper_kind else None,
            abstract_available=bool(paper.abstract_excerpt),
        )
        stored = dict(conversation.generated_artifacts or {})
        stored["selected_paper"] = selected.model_dump(mode="json")
        stored["paper_analysis"] = analysis.model_dump(mode="json")
        conversation.generated_artifacts = stored
        db.add(conversation)
        db.commit()
        return analysis

    def save_notebook_note(
        self,
        conversation_id: str,
        bundle_id: str,
        request: SaveResearchNotebookNoteRequest,
        db: Session,
    ) -> SavedResearchNotebookNote:
        """Archive selected, verified bundle papers in the target Learning session."""
        conversation = self._get_conversation(conversation_id, db)
        record = (
            db.query(ResearchEvidenceBundleModel)
            .filter(
                ResearchEvidenceBundleModel.id == bundle_id,
                ResearchEvidenceBundleModel.conversation_id == conversation_id,
            )
            .first()
        )
        if record is None:
            raise ConversationPaperNotFoundError(bundle_id)
        bundle = ConversationEvidenceBundle.model_validate(record.bundle_data)
        papers_by_url = {paper.url: paper for paper in bundle.papers}
        if any(url not in papers_by_url for url in request.selected_paper_urls):
            raise ConversationPaperNotFoundError("selected paper is not in the evidence bundle")

        profile = ResearchProfile.model_validate(conversation.profile_data)
        question = next(iter(profile.research_questions or profile.candidate_questions), None)
        research_topic = profile.topic or bundle.query
        research_question = question or bundle.query
        selected_urls = sorted(request.selected_paper_urls)
        evidence_refs = [
            _evidence_reference(bundle_id, papers_by_url[url])
            for url in selected_urls
        ]
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.can_prepare_search
        )
        next_steps = (
            [entry.content for entry in plan.two_week_mvp_plan[:3]]
            if plan is not None
            else ["继续完善科研画像并确认下一步研究计划。"]
        )
        note_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "|".join(
                    [
                        conversation_id,
                        bundle_id,
                        request.learning_session_id,
                        *selected_urls,
                    ]
                ),
            )
        )
        payload = SavedResearchNotebookNote(
            notebook_item_id=note_id,
            learning_session_id=request.learning_session_id,
            conversation_id=conversation_id,
            bundle_id=bundle_id,
            research_topic=research_topic,
            research_question=research_question,
            evidence_refs=evidence_refs,
            next_steps=next_steps,
        )
        if db.get(NotebookItemModel, note_id) is None:
            sources = "；".join(
                f"{item.title}（{item.source_name}{f'，{item.year}' if item.year else ''}）"
                + (f"：{item.evidence_summary}" if item.evidence_summary else "")
                for item in evidence_refs
            )
            db.add(
                NotebookItemModel(
                    id=note_id,
                    user_id=conversation.owner_principal_id or "poc-user",
                    owner_principal_id=conversation.owner_principal_id,
                    session_id=request.learning_session_id,
                    knowledge_id=f"research:{conversation_id}"[:64],
                    item_type="research_note",
                    content=(
                        f"研究主题：{research_topic}\n"
                        f"研究问题：{research_question}\n"
                        f"主要证据：{sources}\n"
                        f"下一步建议：{'；'.join(next_steps)}"
                    ),
                    extra_data=payload.model_dump(mode="json"),
                )
            )
            db.commit()
        return payload

    def _cached_bundle(
        self,
        conversation_id: str,
        query: str,
        sources: list[str],
        db: Session,
    ) -> ConversationEvidenceBundle | None:
        expected_sources = list(dict.fromkeys(sources or ["cnki", "crossref", "semantic_scholar"]))
        bundles = (
            db.query(ResearchEvidenceBundleModel)
            .filter(ResearchEvidenceBundleModel.conversation_id == conversation_id)
            .order_by(ResearchEvidenceBundleModel.created_at.desc())
            .all()
        )
        for row in bundles:
            bundle = ConversationEvidenceBundle.model_validate(row.bundle_data)
            if (
                " ".join(bundle.query.split()).casefold() == " ".join(query.split()).casefold()
                and bundle.requested_sources == expected_sources
            ):
                return bundle
        return None

    @staticmethod
    def _profile(
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ResearchProfile:
        conversation = ResearchConversationSearchService._get_conversation(
            conversation_id, db, owned_ids=owned_ids
        )
        return ResearchProfile.model_validate(conversation.profile_data)

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
        return conversation


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


def _evidence_reference(bundle_id: str, paper: AcademicPaperResult) -> EvidenceReference:
    return EvidenceReference(
        bundle_id=bundle_id,
        paper_url=paper.url,
        title=paper.title,
        source_name=paper.source_name,
        year=paper.year,
        evidence_level="abstract" if paper.abstract_excerpt else "metadata",
        evidence_summary=paper.abstract_excerpt[:1000] if paper.abstract_excerpt else None,
    )


def _bundle_paper_id(bundle_id: str, paper: dict[str, object]) -> str:
    identity = next(
        (
            str(value).strip().casefold()
            for value in (
                paper.get("doi"),
                paper.get("arxiv_id"),
                paper.get("identifier"),
                paper.get("url"),
                paper.get("title"),
            )
            if value and str(value).strip()
        ),
        "unknown-paper",
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{bundle_id}|{identity}"))


__all__ = [
    "ConversationPaperNotFoundError",
    "ConversationSearchNotReadyError",
    "ResearchConversationSearchService",
]
