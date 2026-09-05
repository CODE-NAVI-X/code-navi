"""FastAPI router for the rules-driven research-clarification workflow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from code_navi.auth.dependencies import (
    CurrentPrincipal,
    get_optional_principal,
    get_owned_principal_ids,
)
from code_navi.db import get_db
from code_navi.providers import ProviderConfigurationError

from .conversation_guidance import (
    ResearchConversationGuidanceService,
    StudyRecommendationsNotConfirmedError,
)
from .conversation_guidance_schemas import (
    StageBriefingResponse,
    StudyRecommendationRequest,
    StudyRecommendationsResponse,
)
from .conversation_orchestrator import (
    OrchestratorRetryNotApplicableError,
    ResearchConversationOrchestrator,
)
from .conversation_orchestrator_schemas import (
    DirectionCardsResponse,
    LearnerProfileResponse,
    LearnerProfileUpdateRequest,
    LearningContextInput,
    LearningContextState,
    OrchestratorMessageResponse,
    OrchestratorPapersResponse,
    OrchestratorStateResponse,
    SelectPaperRequest,
    SendOrchestratorMessageRequest,
)
from .conversation_schemas import (
    AnalyzeConversationPaperRequest,
    ApplyRevisionSuggestionRequest,
    AssessUnderstandingRequest,
    CitationCandidate,
    CitationQualityCheck,
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    CreateConversationEvidenceBundleRequest,
    CreateExperimentCodeDraftRequest,
    CreateExperimentEvidenceBundleRequest,
    CreatePaperDraftRequest,
    CreateReproductionPipelineRequest,
    CreateResearchConversationRequest,
    CreateSelectedCitationRequest,
    CreateUnderstandingQuestionRequest,
    ExperimentCodeDraft,
    ExperimentDesign,
    ExperimentEvidenceBundle,
    GenerateExperimentDesignRequest,
    GenerateResearchArtifactRequest,
    PaperAnalysis,
    PaperBlueprint,
    PaperDraft,
    PaperExportPackage,
    PaperReview,
    PaperRevision,
    ReadingReport,
    ReadingReportInput,
    ReferenceDraftPackage,
    ReferenceEntryDraft,
    ReproductionConditionsInput,
    ReproductionPipeline,
    ResearchConversationResponse,
    ResearchMindMap,
    ResearchSearchPlan,
    RevisionSuggestion,
    SavedResearchNotebookNote,
    SaveResearchNotebookNoteRequest,
    SelectedCitation,
    SendResearchMessageRequest,
    SubmissionProfile,
    SubmissionProfileInput,
    SubmissionReadinessCheck,
    TopicDifficultyAnalysis,
    UnderstandingCheck,
    UpdateRevisionTaskRequest,
    UpdateSelectedCitationRequest,
)
from .conversation_search_service import (
    ConversationPaperNotFoundError,
    ConversationSearchNotReadyError,
    ResearchConversationSearchService,
)
from .conversation_service import (
    CitationSourceNotFoundError,
    ConversationNotFoundError,
    ReproductionConditionsMissing,
    ReproductionPipelineNotFoundError,
    ResearchConversationService,
    SelectedCitationNotFoundError,
)
from .paper_reading import PaperTextUnavailableError
from .provider_schemas import (
    ConfigureProviderRequest,
    ProviderConnectionTestResponse,
    ProviderStatusResponse,
)
from .provider_service import (
    _provider_connection_service,
    browser_provider_configuration_enabled,
)
from .reproduction_evaluation_schemas import (
    CreateReproductionEvaluationRequest,
    ReproductionImprovementTask,
    ReproductionProjectEvaluationDetail,
    UpdateReproductionImprovementTaskRequest,
)
from .reproduction_evaluation_service import (
    InvalidReproductionTaskTransitionError,
    ReproductionEvaluationNotFoundError,
    ReproductionEvaluationService,
    ReproductionImprovementTaskNotFoundError,
)
from .research_generation import ResearchGenerationError
from .schemas import (
    CreateEvidenceBundleRequest,
    CreateResearchSessionRequest,
    EvidenceBundle,
    ResearchSessionResponse,
    SubmitResearchTurnRequest,
)
from .service import (
    ResearchClarificationService,
    ResearchEvidenceService,
    ResearchPlanRequiredError,
    ResearchSessionNotFoundError,
)

router = APIRouter(prefix="/api/v1/research", tags=["Research"])
_service = ResearchClarificationService()
_evidence_service = ResearchEvidenceService()
_conversation_service = ResearchConversationService()
_conversation_guidance_service = ResearchConversationGuidanceService()
_conversation_search_service = ResearchConversationSearchService()
_reproduction_evaluation_service = ReproductionEvaluationService()
_conversation_orchestrator = ResearchConversationOrchestrator()
_db_dependency = Depends(get_db)
_opt_principal_dep = Depends(get_optional_principal)


def _raise_generation_error(error: ResearchGenerationError) -> None:
    """Surface a failed generation as an explicit, retryable error; never rules prose."""
    status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if error.stage in {"provider_unavailable", "timeout"}
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": "research_generation_failed",
            "stage": error.stage,
            "message": "模型生成失败，本次未生成科研建议。请重试。",
        },
    ) from error


@router.get("/provider/status", response_model=ProviderStatusResponse)
def get_provider_status() -> ProviderStatusResponse:
    """Return model availability without exposing credentials."""
    return _provider_connection_service.status()


@router.put("/provider/configuration", response_model=ProviderStatusResponse)
def configure_provider(
    configuration: ConfigureProviderRequest,
    request: Request,
) -> ProviderStatusResponse:
    """Save a provider secret only when the caller connects from this machine."""
    _require_local_browser_provider_access(request)
    try:
        return _provider_connection_service.configure(configuration)
    except ProviderConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post("/provider/test", response_model=ProviderConnectionTestResponse)
def test_provider_connection(request: Request) -> ProviderConnectionTestResponse:
    """Run one local-only, no-tool structured model connection check."""
    _require_local_browser_provider_test_access(request)
    return _provider_connection_service.test()


def _require_local_browser_provider_access(request: Request) -> None:
    """Guard browser key operations behind explicit local-development opt-in."""
    if not browser_provider_configuration_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前部署已禁用网页 API Key 配置。",
        )
    _require_loopback_browser_client(request)


def _require_local_browser_provider_test_access(request: Request) -> None:
    """Permit an explicit connection test from loopback without browser key writes."""
    _require_loopback_browser_client(request)


def _require_loopback_browser_client(request: Request) -> None:
    """Keep all browser provider operations restricted to the local machine."""
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="网页配置 API Key 仅允许本机访问。",
        )


@router.post(
    "/conversations",
    response_model=ResearchConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    request: CreateResearchConversationRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Start a dynamic research conversation without a fixed questionnaire."""
    principal_id = principal.principal_id if principal else None
    try:
        return _conversation_service.create(request, db, owner_principal_id=principal_id)
    except ResearchGenerationError as error:
        _raise_generation_error(error)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ResearchConversationResponse,
)
def send_conversation_message(
    conversation_id: str,
    request: SendResearchMessageRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Process one free-form message through the conversational workflow."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.send_message(
            conversation_id, request, db, owned_ids=owned_ids
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.post(
    "/conversations/{conversation_id}/messages/retry-last",
    response_model=ResearchConversationResponse,
)
def retry_last_failed_reply(
    conversation_id: str,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Regenerate the latest failed model reply; the user message is preserved."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.retry_last_reply(
            conversation_id, db, owned_ids=owned_ids
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except ResearchGenerationError as error:
        _raise_generation_error(error)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ResearchConversationResponse,
)
def get_conversation(
    conversation_id: str,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Restore a conversation without performing another Agent run."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.get(conversation_id, db, owned_ids=owned_ids)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/stage-briefing",
    response_model=StageBriefingResponse,
)
def get_stage_briefing(
    conversation_id: str,
    include_evidence_trends: bool = False,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> StageBriefingResponse:
    """Return the pure-rule first-screen stage briefing (contract §2.1)."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_guidance_service.stage_briefing(
            conversation_id,
            db,
            owned_ids=owned_ids,
            include_evidence_trends=include_evidence_trends,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.post(
    "/conversations/{conversation_id}/study-recommendations",
    response_model=StudyRecommendationsResponse,
)
def create_study_recommendations(
    conversation_id: str,
    request: StudyRecommendationRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> StudyRecommendationsResponse:
    """Return explicitly triggered pure-rule study recommendations (contract §2.2)."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_guidance_service.study_recommendations(
            conversation_id, request, db, owned_ids=owned_ids
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error
    except StudyRecommendationsNotConfirmedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Study recommendations require explicit user confirmation.",
        ) from error


@router.put(
    "/conversations/{conversation_id}/submission-profile",
    response_model=SubmissionProfile,
)
def save_submission_profile(
    conversation_id: str,
    request: SubmissionProfileInput,
    db: Session = _db_dependency,
) -> SubmissionProfile:
    """Save only user-known submission constraints; this route never fetches venue rules."""
    try:
        return _conversation_service.save_submission_profile(conversation_id, request, db)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/submission-profile",
    response_model=SubmissionProfile | None,
)
def get_submission_profile(
    conversation_id: str,
    db: Session = _db_dependency,
) -> SubmissionProfile | None:
    """Restore a local submission profile without a model call or network activity."""
    try:
        return _conversation_service.get_submission_profile(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/search-plan",
    response_model=ResearchSearchPlan,
)
def get_conversation_search_plan(
    conversation_id: str,
    db: Session = _db_dependency,
) -> ResearchSearchPlan:
    """Prepare a bounded search plan without performing a network request."""
    try:
        return _conversation_search_service.plan(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationSearchNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/conversations/{conversation_id}/research-plan",
    response_model=ConversationResearchPlan,
)
def generate_conversation_research_plan(
    conversation_id: str,
    request: GenerateResearchArtifactRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ConversationResearchPlan:
    """Generate the visible research plan only after an explicit user action."""
    if not request.user_confirmed:
        raise HTTPException(status_code=422, detail="请先确认生成研究计划。")
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.generate_research_plan(
            conversation_id, db, owned_ids=owned_ids
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/conversations/{conversation_id}/evidence-bundles",
    response_model=ConversationEvidenceBundle,
)
def create_conversation_evidence_bundle(
    conversation_id: str,
    request: CreateConversationEvidenceBundleRequest,
    db: Session = _db_dependency,
) -> ConversationEvidenceBundle:
    """Run one explicitly confirmed, source-restricted academic search."""
    try:
        return _conversation_search_service.search(conversation_id, request, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationSearchNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/conversations/{conversation_id}/evidence-bundles",
    response_model=list[ConversationEvidenceBundle],
)
def list_conversation_evidence_bundles(
    conversation_id: str,
    db: Session = _db_dependency,
) -> list[ConversationEvidenceBundle]:
    """Restore saved evidence bundles without accessing external sources."""
    try:
        return _conversation_search_service.list_bundles(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/reading-reports",
    response_model=list[ReadingReport],
    status_code=status.HTTP_201_CREATED,
)
def save_reading_report(
    conversation_id: str,
    request: ReadingReportInput,
    db: Session = _db_dependency,
) -> list[ReadingReport]:
    """Store the user's own reading summary; it stays user-sourced."""
    try:
        return _conversation_service.save_reading_report(conversation_id, request, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get(
    "/conversations/{conversation_id}/reading-reports",
    response_model=list[ReadingReport],
)
def list_reading_reports(
    conversation_id: str, db: Session = _db_dependency
) -> list[ReadingReport]:
    """Restore the conversation's reading reports verbatim."""
    try:
        return _conversation_service.list_reading_reports(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.put(
    "/conversations/{conversation_id}/reproduction-conditions",
    response_model=ResearchConversationResponse,
)
def save_reproduction_conditions(
    conversation_id: str,
    request: ReproductionConditionsInput,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Store user-provided hardware/time/goal conditions before planning."""
    try:
        return _conversation_service.save_reproduction_conditions(
            conversation_id, request, db
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/reproduction-pipelines",
    response_model=ReproductionPipeline,
    status_code=status.HTTP_201_CREATED,
)
def create_reproduction_pipeline(
    conversation_id: str,
    request: CreateReproductionPipelineRequest,
    db: Session = _db_dependency,
) -> ReproductionPipeline:
    """Create a model-written plan from one user-selected already-saved paper."""
    try:
        return _conversation_service.create_reproduction_pipeline(conversation_id, request, db)
    except ReproductionConditionsMissing as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "reproduction_conditions_missing",
                "missing": error.missing,
                "message": "请先补齐硬件、可用时间和复现目标，再生成复现方案。",
            },
        ) from error
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ReproductionPipelineNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Selected paper is not present in this conversation's saved evidence.",
        ) from error
    except PaperTextUnavailableError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/conversations/{conversation_id}/reproduction-pipelines",
    response_model=list[ReproductionPipeline],
)
def list_reproduction_pipelines(
    conversation_id: str, db: Session = _db_dependency
) -> list[ReproductionPipeline]:
    """Restore saved Pipelines without regenerating or searching."""
    try:
        return _conversation_service.list_reproduction_pipelines(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get("/reproduction-pipelines/{pipeline_id}", response_model=ReproductionPipeline)
def get_reproduction_pipeline(
    pipeline_id: str, db: Session = _db_dependency
) -> ReproductionPipeline:
    """Load one stable Pipeline contract for later local consumers."""
    try:
        return _conversation_service.get_reproduction_pipeline(pipeline_id, db)
    except ReproductionPipelineNotFoundError as error:
        raise HTTPException(status_code=404, detail="Reproduction pipeline not found.") from error


@router.get(
    "/conversations/{conversation_id}/citation-candidates",
    response_model=list[CitationCandidate],
)
def list_citation_candidates(
    conversation_id: str, db: Session = _db_dependency
) -> list[CitationCandidate]:
    """List only already-saved, source-restricted evidence; this endpoint never searches."""
    try:
        return _conversation_service.list_citation_candidates(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/selected-citations",
    response_model=SelectedCitation,
    status_code=status.HTTP_201_CREATED,
)
def create_selected_citation(
    conversation_id: str,
    request: CreateSelectedCitationRequest,
    db: Session = _db_dependency,
) -> SelectedCitation:
    """Persist a user-selected local citation placeholder without changing draft text."""
    try:
        return _conversation_service.create_selected_citation(conversation_id, request, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except CitationSourceNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Evidence source is not present in this conversation's saved bundle.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/selected-citations",
    response_model=list[SelectedCitation],
)
def list_selected_citations(
    conversation_id: str, db: Session = _db_dependency
) -> list[SelectedCitation]:
    """Restore local citation choices without automatic insertion or external access."""
    try:
        return _conversation_service.list_selected_citations(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.patch("/selected-citations/{selected_citation_id}", response_model=SelectedCitation)
def update_selected_citation(
    selected_citation_id: str,
    request: UpdateSelectedCitationRequest,
    db: Session = _db_dependency,
) -> SelectedCitation:
    """Track an explicit user status only; the server never inserts citation text."""
    try:
        return _conversation_service.update_selected_citation(selected_citation_id, request, db)
    except SelectedCitationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Selected citation not found.") from error


@router.get(
    "/conversations/{conversation_id}/reference-entry-drafts",
    response_model=list[ReferenceEntryDraft],
)
def list_reference_entry_drafts(
    conversation_id: str, db: Session = _db_dependency
) -> list[ReferenceEntryDraft]:
    """Return readable drafts only for sources the user explicitly retained."""
    try:
        return _conversation_service.list_reference_entry_drafts(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get(
    "/conversations/{conversation_id}/reference-draft-package",
    response_model=ReferenceDraftPackage,
)
def get_reference_draft_package(
    conversation_id: str, db: Session = _db_dependency
) -> ReferenceDraftPackage:
    """Return stable, traceable text and one consolidated human-review checklist."""
    try:
        return _conversation_service.get_reference_draft_package(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/citation-quality-checks",
    response_model=CitationQualityCheck,
    status_code=status.HTTP_201_CREATED,
)
def create_citation_quality_check(
    conversation_id: str, db: Session = _db_dependency
) -> CitationQualityCheck:
    """Explicitly inspect saved citation choices without network or draft mutation."""
    try:
        return _conversation_service.create_citation_quality_check(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get(
    "/conversations/{conversation_id}/citation-quality-checks",
    response_model=list[CitationQualityCheck],
)
def list_citation_quality_checks(
    conversation_id: str, db: Session = _db_dependency
) -> list[CitationQualityCheck]:
    """Restore persisted citation checks without re-running them."""
    try:
        return _conversation_service.list_citation_quality_checks(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/evidence-bundles/{bundle_id}/notebook-notes",
    response_model=SavedResearchNotebookNote,
)
def save_conversation_evidence_as_notebook_note(
    conversation_id: str,
    bundle_id: str,
    request: SaveResearchNotebookNoteRequest,
    db: Session = _db_dependency,
) -> SavedResearchNotebookNote:
    """Save user-selected evidence as a traceable Learning research note."""
    try:
        return _conversation_search_service.save_notebook_note(
            conversation_id, bundle_id, request, db
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationPaperNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Evidence bundle or selected paper was not found in this conversation.",
        ) from error


@router.post(
    "/conversations/{conversation_id}/paper-analysis",
    response_model=PaperAnalysis,
)
def analyze_conversation_paper(
    conversation_id: str,
    request: AnalyzeConversationPaperRequest,
    db: Session = _db_dependency,
) -> PaperAnalysis:
    """Analyze only metadata/abstract from a user-selected saved evidence item."""
    try:
        return _conversation_search_service.analyze_paper(conversation_id, request, db)
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationPaperNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Paper is not present in this conversation's saved evidence bundles.",
        ) from error
    except PaperTextUnavailableError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/conversations/{conversation_id}/paper-analysis/upload",
    response_model=PaperAnalysis,
)
async def analyze_conversation_paper_upload(
    conversation_id: str,
    request: Request,
    paper_url: str = Query(..., min_length=1, max_length=2000),
    db: Session = _db_dependency,
) -> PaperAnalysis:
    """Analyze a selected saved paper from a user-uploaded local PDF."""
    try:
        payload = await request.body()
        return _conversation_search_service.analyze_paper_upload(
            conversation_id,
            paper_url=paper_url,
            payload=payload,
            filename=request.headers.get("x-filename"),
            db=db,
        )
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationPaperNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Paper is not present in this conversation's saved evidence bundles.",
        ) from error
    except PaperTextUnavailableError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/conversations/{conversation_id}/research-mindmap",
    response_model=ResearchMindMap,
)
def generate_research_mindmap(
    conversation_id: str,
    request: GenerateResearchArtifactRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ResearchMindMap:
    """Generate a persisted, source-bounded map only after explicit confirmation."""
    del request
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.generate_research_mindmap(
            conversation_id, db, owned_ids=owned_ids
        )
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/topic-difficulty-analysis",
    response_model=TopicDifficultyAnalysis,
)
def generate_topic_difficulty_analysis(
    conversation_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> TopicDifficultyAnalysis:
    """Run one audited personalization after explicit user confirmation."""
    del request
    try:
        return _conversation_service.generate_topic_difficulty_analysis(conversation_id, db)
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/experiment-design",
    response_model=ExperimentDesign,
)
def generate_experiment_design(
    conversation_id: str,
    request: GenerateExperimentDesignRequest,
    db: Session = _db_dependency,
) -> ExperimentDesign:
    """Run one audited experiment-design personalization after confirmation."""
    try:
        design = _conversation_service.generate_experiment_design(
            conversation_id,
            db,
            task_type_override=request.task_type_override,
        )
        if design is None:
            raise HTTPException(
                status_code=409,
                detail="当前科研画像尚未形成规则研究计划。",
            )
        return design
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/understanding-checks/question",
    response_model=UnderstandingCheck,
)
def create_understanding_question(
    conversation_id: str,
    request: CreateUnderstandingQuestionRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> UnderstandingCheck:
    """Generate one section-bound comprehension question for an explicit paper."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.create_understanding_question(
            conversation_id, request, db, owned_ids=owned_ids
        )
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationPaperNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Paper is not present in this conversation's saved evidence bundles.",
        ) from error


@router.post(
    "/conversations/{conversation_id}/understanding-checks/assess",
    response_model=UnderstandingCheck,
)
def assess_understanding_answer(
    conversation_id: str,
    request: AssessUnderstandingRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> UnderstandingCheck:
    """Assess a user-submitted answer; failures retain the answer and last success."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.assess_understanding_answer(
            conversation_id, request, db, owned_ids=owned_ids
        )
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationPaperNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Paper is not present in this conversation's saved evidence bundles.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/understanding-checks",
    response_model=list[UnderstandingCheck],
)
def list_understanding_checks(
    conversation_id: str,
    paper_url: str = Query(..., min_length=1, max_length=2000),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> list[UnderstandingCheck]:
    """Restore per-section last-success checks for one paper without a model call."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_service.list_understanding_checks(
            conversation_id, paper_url, db, owned_ids=owned_ids
        )
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/experiment-code-draft",
    response_model=ExperimentCodeDraft,
)
def create_experiment_code_draft(
    conversation_id: str,
    request: CreateExperimentCodeDraftRequest,
    db: Session = _db_dependency,
) -> ExperimentCodeDraft:
    """Return preview code only after the request explicitly confirms intent."""
    try:
        return _conversation_service.create_experiment_code_draft(conversation_id, db)
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/experiment-evidence-bundles",
    response_model=ExperimentEvidenceBundle,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment_evidence_bundle(
    conversation_id: str,
    request: CreateExperimentEvidenceBundleRequest,
    db: Session = _db_dependency,
) -> ExperimentEvidenceBundle:
    """Save explicit text evidence only; no model, file access, or network call occurs."""
    try:
        return _conversation_service.create_experiment_evidence_bundle(conversation_id, request, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get(
    "/conversations/{conversation_id}/experiment-evidence-bundles",
    response_model=list[ExperimentEvidenceBundle],
)
def list_experiment_evidence_bundles(
    conversation_id: str,
    db: Session = _db_dependency,
) -> list[ExperimentEvidenceBundle]:
    """Restore saved user-submitted evidence without reading files or the network."""
    try:
        return _conversation_service.list_experiment_evidence_bundles(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/reproduction-evaluations",
    status_code=201,
    response_model=ReproductionProjectEvaluationDetail,
)
def create_reproduction_evaluation(
    conversation_id: str,
    request: CreateReproductionEvaluationRequest,
    db: Session = _db_dependency,
) -> ReproductionProjectEvaluationDetail:
    """Persist one explicit offline evaluation; never execute or retrieve anything."""
    del request
    try:
        return _reproduction_evaluation_service.create(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get(
    "/conversations/{conversation_id}/reproduction-evaluations",
    response_model=list[ReproductionProjectEvaluationDetail],
)
def list_reproduction_evaluations(
    conversation_id: str,
    db: Session = _db_dependency,
) -> list[ReproductionProjectEvaluationDetail]:
    """Restore saved evaluation snapshots and current improvement-task states."""
    try:
        return _reproduction_evaluation_service.list(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get(
    "/reproduction-evaluations/{evaluation_id}",
    response_model=ReproductionProjectEvaluationDetail,
)
def get_reproduction_evaluation(
    evaluation_id: str,
    db: Session = _db_dependency,
) -> ReproductionProjectEvaluationDetail:
    """Restore one saved evaluation without re-running its rules."""
    try:
        return _reproduction_evaluation_service.get(evaluation_id, db)
    except ReproductionEvaluationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Reproduction evaluation not found.") from error


@router.patch(
    "/reproduction-improvement-tasks/{task_id}",
    response_model=ReproductionImprovementTask,
)
def update_reproduction_improvement_task(
    task_id: str,
    request: UpdateReproductionImprovementTaskRequest,
    db: Session = _db_dependency,
) -> ReproductionImprovementTask:
    """Record an explicit accept, skip, or complete action for one task."""
    try:
        return _reproduction_evaluation_service.update_task(task_id, request, db)
    except ReproductionImprovementTaskNotFoundError as error:
        raise HTTPException(status_code=404, detail="Improvement task not found.") from error
    except InvalidReproductionTaskTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/conversations/{conversation_id}/paper-blueprint",
    response_model=PaperBlueprint,
)
def generate_paper_blueprint(
    conversation_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> PaperBlueprint:
    """Create a source-bounded model paper outline after explicit confirmation."""
    del request
    try:
        return _conversation_service.generate_paper_blueprint(conversation_id, db)
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/paper-drafts",
    response_model=PaperDraft,
    status_code=status.HTTP_201_CREATED,
)
def create_paper_draft(
    conversation_id: str,
    request: CreatePaperDraftRequest,
    db: Session = _db_dependency,
) -> PaperDraft:
    """Save only user-pasted Markdown/plain text for the current local session."""
    try:
        return _conversation_service.create_paper_draft(conversation_id, request, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.get("/conversations/{conversation_id}/paper-drafts", response_model=list[PaperDraft])
def list_paper_drafts(conversation_id: str, db: Session = _db_dependency) -> list[PaperDraft]:
    """Restore local-session draft metadata without external access."""
    try:
        return _conversation_service.list_paper_drafts(conversation_id, db)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post("/paper-drafts/{draft_id}/reviews", response_model=PaperReview)
def create_paper_review(
    draft_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> PaperReview:
    """Generate rules-first review findings after the user explicitly asks."""
    del request
    try:
        return _conversation_service.create_paper_review(draft_id, db)
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found.") from error


@router.get("/paper-drafts/{draft_id}/reviews", response_model=list[PaperReview])
def list_paper_reviews(draft_id: str, db: Session = _db_dependency) -> list[PaperReview]:
    try:
        return _conversation_service.list_paper_reviews(draft_id, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found.") from error


@router.patch("/paper-reviews/{review_id}/revision-tasks/{task_id}", response_model=PaperReview)
def update_revision_task(
    review_id: str,
    task_id: str,
    request: UpdateRevisionTaskRequest,
    db: Session = _db_dependency,
) -> PaperReview:
    """Record one explicit accept/skip decision; it never changes the original draft."""
    try:
        return _conversation_service.update_revision_task(review_id, task_id, request, db)
    except LookupError as error:
        raise HTTPException(
            status_code=404, detail="Paper review or revision task not found."
        ) from error


@router.post(
    "/paper-reviews/{review_id}/revision-tasks/{task_id}/suggestions",
    response_model=RevisionSuggestion,
    status_code=status.HTTP_201_CREATED,
)
def create_revision_suggestion(
    review_id: str,
    task_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> RevisionSuggestion:
    """Generate one candidate only after the user accepted its revision task."""
    del request
    try:
        return _conversation_service.create_revision_suggestion(review_id, task_id, db)
    except ResearchGenerationError as error:
        _raise_generation_error(error)
    except LookupError as error:
        raise HTTPException(
            status_code=404, detail="Paper review or revision task not found."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/paper-reviews/{review_id}/revision-tasks/{task_id}/suggestions",
    response_model=list[RevisionSuggestion],
)
def list_revision_suggestions(
    review_id: str, task_id: str, db: Session = _db_dependency
) -> list[RevisionSuggestion]:
    try:
        return _conversation_service.list_revision_suggestions(review_id, task_id, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper review not found.") from error


@router.post(
    "/revision-suggestions/{suggestion_id}/apply",
    response_model=PaperRevision | None,
    status_code=status.HTTP_201_CREATED,
)
def apply_revision_suggestion(
    suggestion_id: str,
    request: ApplyRevisionSuggestionRequest,
    db: Session = _db_dependency,
) -> PaperRevision | None:
    """Create a new immutable version only after an explicit candidate decision."""
    try:
        return _conversation_service.apply_revision_suggestion(suggestion_id, request, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Revision suggestion not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/paper-reviews/{review_id}/revisions",
    response_model=PaperRevision,
    status_code=status.HTTP_201_CREATED,
)
def create_paper_revision(review_id: str, db: Session = _db_dependency) -> PaperRevision:
    """Retire the former bulk-preview endpoint in favor of explicit paragraph candidates."""
    del review_id, db
    raise HTTPException(
        status_code=409,
        detail="不再支持一次性生成多任务修订预览；请先接受任务，再逐段生成并确认候选改写。",
    )


@router.get("/paper-drafts/{draft_id}/revisions", response_model=list[PaperRevision])
def list_paper_revisions(draft_id: str, db: Session = _db_dependency) -> list[PaperRevision]:
    try:
        return _conversation_service.list_paper_revisions(draft_id, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found.") from error


@router.post(
    "/paper-drafts/{draft_id}/submission-readiness",
    response_model=SubmissionReadinessCheck,
    status_code=status.HTTP_201_CREATED,
)
def create_submission_readiness(
    draft_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> SubmissionReadinessCheck:
    """Run local rules only after an explicit user request; it never submits a paper."""
    del request
    try:
        return _conversation_service.create_submission_readiness(draft_id, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found.") from error


@router.get(
    "/paper-drafts/{draft_id}/submission-readiness",
    response_model=list[SubmissionReadinessCheck],
)
def list_submission_readiness(
    draft_id: str, db: Session = _db_dependency
) -> list[SubmissionReadinessCheck]:
    try:
        return _conversation_service.list_submission_readiness(draft_id, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found.") from error


@router.post("/paper-drafts/{draft_id}/export-package", response_model=PaperExportPackage)
def create_paper_export_package(
    draft_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> PaperExportPackage:
    """Return safe local text; the browser download remains a separate user action."""
    del request
    try:
        return _conversation_service.create_paper_export_package(draft_id, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/sessions",
    response_model=ResearchSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    request: CreateResearchSessionRequest,
    db: Session = _db_dependency,
) -> ResearchSessionResponse:
    """Create a new rules-driven research-clarification session."""
    return _service.create(request, db)


@router.post("/sessions/{session_id}/turns", response_model=ResearchSessionResponse)
def submit_turn(
    session_id: str,
    request: SubmitResearchTurnRequest,
    db: Session = _db_dependency,
) -> ResearchSessionResponse:
    """Record one recommended or free-text answer and return the next rule step."""
    try:
        return _service.advance(session_id, request, db)
    except ResearchSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        ) from error


@router.get("/sessions/{session_id}", response_model=ResearchSessionResponse)
def get_session(
    session_id: str,
    db: Session = _db_dependency,
) -> ResearchSessionResponse:
    """Restore a persisted research-clarification session by identifier."""
    try:
        return _service.get(session_id, db)
    except ResearchSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        ) from error


@router.post(
    "/sessions/{session_id}/evidence-bundles",
    response_model=EvidenceBundle,
)
def create_evidence_bundle(
    session_id: str,
    request: CreateEvidenceBundleRequest,
    db: Session = _db_dependency,
) -> EvidenceBundle:
    """Run one user-triggered, source-restricted academic metadata search."""
    try:
        return _evidence_service.create_bundle(session_id, request, db)
    except ResearchSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found."
        ) from error
    except ResearchPlanRequiredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/conversations/{conversation_id}/orchestrator/messages",
    response_model=OrchestratorMessageResponse,
)
def send_orchestrator_message(
    conversation_id: str,
    request: SendOrchestratorMessageRequest,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> OrchestratorMessageResponse:
    """Send a message to Jiang Jiang with deterministic state machine and tool orchestration."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.process_message(
            conversation_id,
            request,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.post(
    "/conversations/{conversation_id}/orchestrator/messages/stream",
    response_class=StreamingResponse,
)
def stream_orchestrator_message(
    conversation_id: str,
    request: SendOrchestratorMessageRequest,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> StreamingResponse:
    """Stream orchestrator thinking lifecycle events (thinking -> completed/failed)."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        generator = _conversation_orchestrator.stream_message(
            conversation_id,
            request,
            db,
            owned_ids=owned_ids,
        )
        return StreamingResponse(generator, media_type="text/event-stream")
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.post(
    "/conversations/{conversation_id}/orchestrator/messages/retry-last",
    response_model=OrchestratorMessageResponse,
)
def retry_last_orchestrator_message(
    conversation_id: str,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> OrchestratorMessageResponse:
    """Retry the last failed turn in the conversation orchestrator."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.retry_last_message(
            conversation_id,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error
    except OrchestratorRetryNotApplicableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.get(
    "/conversations/{conversation_id}/orchestrator/state",
    response_model=OrchestratorStateResponse,
)
def get_orchestrator_state(
    conversation_id: str,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> OrchestratorStateResponse:
    """Read the four-stage state machine and subtasks status for a conversation."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.get_or_create_state(
            conversation_id,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/orchestrator/direction-cards",
    response_model=DirectionCardsResponse,
)
def get_orchestrator_direction_cards(
    conversation_id: str,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> DirectionCardsResponse:
    """Get dynamically generated direction cards based on learning input."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.get_direction_cards(
            conversation_id,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/orchestrator/papers",
    response_model=OrchestratorPapersResponse,
)
def get_orchestrator_papers(
    conversation_id: str,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> OrchestratorPapersResponse:
    """Get current active paper and full selection history."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.get_papers(
            conversation_id,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.post(
    "/conversations/{conversation_id}/orchestrator/papers/select",
    response_model=OrchestratorPapersResponse,
)
def select_orchestrator_paper(
    conversation_id: str,
    request: SelectPaperRequest,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> OrchestratorPapersResponse:
    """Select a paper with explicit purpose (replace, compare, cite)."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.select_paper(
            conversation_id,
            request,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/orchestrator/learner-profiles",
    response_model=LearnerProfileResponse,
)
def get_orchestrator_learner_profiles(
    conversation_id: str,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> LearnerProfileResponse:
    """Get current learner profile version and history."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.get_learner_profiles(
            conversation_id,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.put(
    "/conversations/{conversation_id}/orchestrator/learner-profiles",
    response_model=LearnerProfileResponse,
)
def update_orchestrator_learner_profile(
    conversation_id: str,
    request: LearnerProfileUpdateRequest,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> LearnerProfileResponse:
    """Update learner profile, creating a new version."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.update_learner_profile(
            conversation_id,
            request,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}/orchestrator/learning-context",
    response_model=LearningContextState,
)
def get_orchestrator_learning_context(
    conversation_id: str,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> LearningContextState:
    """Get learning input context or empty state."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _conversation_orchestrator.get_learning_context(
            conversation_id,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.put(
    "/conversations/{conversation_id}/orchestrator/learning-context",
    response_model=LearningContextState,
)
def update_orchestrator_learning_context(
    conversation_id: str,
    request: LearningContextInput,
    principal: CurrentPrincipal = _opt_principal_dep,
    db: Session = _db_dependency,
) -> LearningContextState:
    """Receive and store learning context inputs."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        state = _conversation_orchestrator.update_learning_context(
            conversation_id,
            request,
            db,
            owned_ids=owned_ids,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error
    # 首次写入有效学习输入后，幂等触发一次新版桥接欢迎语（welcome_and_bridge）。
    # 触发失败只体现在会话状态的 failed 语义里，不改变 PUT 的返回契约。
    _conversation_orchestrator.ensure_bridge_welcome(
        conversation_id, db, owned_ids=owned_ids
    )
    return state
