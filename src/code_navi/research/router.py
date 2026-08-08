"""FastAPI router for the rules-driven research-clarification workflow."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from code_navi.db import get_db
from code_navi.providers import ProviderConfigurationError

from .conversation_schemas import (
    AnalyzeConversationPaperRequest,
    ConversationEvidenceBundle,
    CreateConversationEvidenceBundleRequest,
    CreateExperimentCodeDraftRequest,
    CreateExperimentEvidenceBundleRequest,
    CreatePaperDraftRequest,
    CreateResearchConversationRequest,
    ExperimentCodeDraft,
    ExperimentDesign,
    ExperimentEvidenceBundle,
    GenerateResearchArtifactRequest,
    PaperAnalysis,
    PaperBlueprint,
    PaperDraft,
    PaperExportPackage,
    PaperReview,
    PaperRevision,
    ResearchConversationResponse,
    ResearchSearchPlan,
    SendResearchMessageRequest,
    SubmissionReadinessCheck,
    TopicDifficultyAnalysis,
    UpdateRevisionTaskRequest,
)
from .conversation_search_service import (
    ConversationPaperNotFoundError,
    ConversationSearchNotReadyError,
    ResearchConversationSearchService,
)
from .conversation_service import (
    ConversationNotFoundError,
    ResearchConversationService,
)
from .provider_schemas import (
    ConfigureProviderRequest,
    ProviderConnectionTestResponse,
    ProviderStatusResponse,
)
from .provider_service import _provider_connection_service
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
_conversation_search_service = ResearchConversationSearchService()
_db_dependency = Depends(get_db)


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
    _require_local_browser_provider_access(request)
    return _provider_connection_service.test()


def _require_local_browser_provider_access(request: Request) -> None:
    """Guard browser key operations behind explicit local-development opt-in."""
    browser_configuration_enabled = os.getenv(
        "CODE_NAVI_ALLOW_BROWSER_PROVIDER_CONFIG", "false"
    ).lower() in {"1", "true", "yes", "on"}
    if not browser_configuration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前部署已禁用网页 API Key 配置。",
        )
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
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Start a dynamic research conversation without a fixed questionnaire."""
    return _conversation_service.create(request, db)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ResearchConversationResponse,
)
def send_conversation_message(
    conversation_id: str,
    request: SendResearchMessageRequest,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Process one free-form message through the conversational workflow."""
    try:
        return _conversation_service.send_message(conversation_id, request, db)
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        ) from error


@router.get(
    "/conversations/{conversation_id}",
    response_model=ResearchConversationResponse,
)
def get_conversation(
    conversation_id: str,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Restore a conversation without performing another Agent run."""
    try:
        return _conversation_service.get(conversation_id, db)
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
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error
    except ConversationPaperNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Paper is not present in this conversation's saved evidence bundles.",
        ) from error


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
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found.") from error


@router.post(
    "/conversations/{conversation_id}/experiment-design",
    response_model=ExperimentDesign,
)
def generate_experiment_design(
    conversation_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> ExperimentDesign:
    """Run one audited experiment-design personalization after confirmation."""
    del request
    try:
        design = _conversation_service.generate_experiment_design(conversation_id, db)
        if design is None:
            raise HTTPException(
                status_code=409,
                detail="当前科研画像尚未形成规则研究计划。",
            )
        return design
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
        return _conversation_service.create_experiment_evidence_bundle(
            conversation_id, request, db
        )
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
    "/conversations/{conversation_id}/paper-blueprint",
    response_model=PaperBlueprint,
)
def generate_paper_blueprint(
    conversation_id: str,
    request: GenerateResearchArtifactRequest,
    db: Session = _db_dependency,
) -> PaperBlueprint:
    """Create a rules-only paper outline after an explicit user confirmation."""
    del request
    try:
        return _conversation_service.generate_paper_blueprint(conversation_id, db)
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
    "/paper-reviews/{review_id}/revisions",
    response_model=PaperRevision,
    status_code=status.HTTP_201_CREATED,
)
def create_paper_revision(review_id: str, db: Session = _db_dependency) -> PaperRevision:
    """Create a preview only for accepted tasks, preserving every original version."""
    try:
        return _conversation_service.create_paper_revision(review_id, db)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Paper review not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
