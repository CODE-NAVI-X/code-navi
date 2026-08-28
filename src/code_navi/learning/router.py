"""Independent API router for the learning module."""

from __future__ import annotations

import json
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from code_navi.auth.dependencies import (
    CurrentPrincipal,
    get_optional_principal,
    get_owned_principal_ids,
)
from code_navi.db import get_db
from code_navi.workspaces.models import WorkspaceActivityModel, WorkspaceModel
from code_navi.workspaces.service import (
    TaskNotFoundError,
    WorkspaceConflictError,
    WorkspaceNotFoundError,
    WorkspaceService,
)

from ..learning_profile.schemas import (
    UUID_V4_PATTERN,
    KnowledgeGapResponse,
    MarkRequest,
    MarkResponse,
)
from ..learning_profile.service import ProfileService
from .models import NotebookItemModel
from .presentation.schemas import PresentationGenerateRequest
from .presentation.services import PresentationGenerator
from .quiz.docx import export_quiz_docx
from .quiz.schemas import GradeRequest, GradeResponse, QuizGenerateRequest, QuizGenerateResponse
from .quiz.services import QuizGenerator, QuizNotFoundError
from .schemas import (
    Citation,
    ExplainRequest,
    ExplainResponse,
    RecentLearningItem,
    RecentLearningListResponse,
)
from .services import QueryOrchestrator

router = APIRouter(prefix="/api/v1/learning", tags=["Learning"])

_orchestrator = QueryOrchestrator()
_presentation_generator = PresentationGenerator()
_quiz_generator = QuizGenerator()
_workspace_service = WorkspaceService()
_profile_service = ProfileService()
_db_dependency = Depends(get_db)
_opt_principal_dep = Depends(get_optional_principal)

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.post("/explain", response_model=ExplainResponse, status_code=200)
async def explain_knowledge_point(
    request: ExplainRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ExplainResponse:
    """Explain a knowledge point with optional citations.

    The pipeline runs decontamination → explanation generation → notebook
    archival, all delegated to ``QueryOrchestrator``.
    """
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    principal_id = principal.principal_id if principal else None
    try:
        if request.local_profile_id is None and not principal_id:
            return _orchestrator.explain(request, db, owner_principal_id=principal_id)

        context = _workspace_service.resolve_learning_context(
            local_profile_id=request.local_profile_id,
            workspace_id=request.workspace_id,
            task_id=request.task_id,
            db=db,
            principal_id=principal_id,
            owned_ids=owned_ids,
        )
        return _orchestrator.explain(
            request,
            db,
            owner_principal_id=principal_id,
            on_notebook_persisted=lambda notebook_item: _workspace_service.record_learning_activity(
                context=context,
                notebook_item=notebook_item,
                db=db,
            ),
        )
    except (TaskNotFoundError, WorkspaceNotFoundError) as error:
        db.rollback()
        raise HTTPException(status_code=404, detail="Workspace or Task not found.") from error
    except WorkspaceConflictError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/recent", response_model=RecentLearningListResponse)
async def list_recent_learning(
    local_profile_id: str | None = Query(None, min_length=1, max_length=64),
    limit: int = Query(4, ge=1, le=12),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> RecentLearningListResponse:
    """Return a small, recoverable Learning history for the current local profile or principal."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    query = (
        db.query(WorkspaceActivityModel, NotebookItemModel)
        .join(WorkspaceModel, WorkspaceActivityModel.workspace_id == WorkspaceModel.id)
        .outerjoin(
            NotebookItemModel,
            NotebookItemModel.id == WorkspaceActivityModel.source_object_id,
        )
        .filter(
            WorkspaceActivityModel.capability == "learning",
            WorkspaceActivityModel.action_type == "knowledge_explained",
            WorkspaceActivityModel.source_object_type == "notebook_item",
        )
    )
    if owned_ids:
        query = query.filter(WorkspaceModel.owner_principal_id.in_(owned_ids))
    elif local_profile_id:
        query = query.filter(WorkspaceModel.owner_scope_id == local_profile_id)
    else:
        return RecentLearningListResponse(items=[])

    rows = (
        query.order_by(WorkspaceActivityModel.created_at.desc(), WorkspaceActivityModel.id.desc())
        .limit(limit)
        .all()
    )
    return RecentLearningListResponse(
        items=[_recent_learning_item(activity, notebook_item) for activity, notebook_item in rows]
    )


@router.get("/recent/{activity_id}", response_model=RecentLearningItem)
async def get_recent_learning(
    activity_id: str,
    local_profile_id: str | None = Query(None, min_length=1, max_length=64),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> RecentLearningItem:
    """Load one persisted Learning source after a user chooses to restore it."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    query = (
        db.query(WorkspaceActivityModel, NotebookItemModel)
        .join(WorkspaceModel, WorkspaceActivityModel.workspace_id == WorkspaceModel.id)
        .outerjoin(
            NotebookItemModel,
            NotebookItemModel.id == WorkspaceActivityModel.source_object_id,
        )
        .filter(
            WorkspaceActivityModel.id == activity_id,
            WorkspaceActivityModel.capability == "learning",
            WorkspaceActivityModel.action_type == "knowledge_explained",
            WorkspaceActivityModel.source_object_type == "notebook_item",
        )
    )
    if owned_ids:
        query = query.filter(WorkspaceModel.owner_principal_id.in_(owned_ids))
    elif local_profile_id:
        query = query.filter(WorkspaceModel.owner_scope_id == local_profile_id)

    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Recent Learning item not found.")
    return _recent_learning_item(*row, include_content=True)


@router.get("/knowledge-gaps", response_model=KnowledgeGapResponse)
async def list_knowledge_gaps(
    profile_id: str = Query(
        ...,
        pattern=UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Unified profile key (UUID v4, == the practice learner_id).",
    ),
    local_profile_id: str | None = Query(None, min_length=1, max_length=64),
    limit: int = Query(50, ge=1, le=100),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> KnowledgeGapResponse:
    """Return traceable review items for the current local Learning portrait.

    This is a read projection only. QuizAttempt and ConfusionMark facts are
    selected by the caller's anonymous ``profile_id``; PracticeOutcome facts are
    additionally scoped by ``local_profile_id`` because they belong to the
    Workspace owner boundary. The endpoint does not create a KnowledgeGap table
    or imply account-level authorization.
    """
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    return _profile_service.get_knowledge_gaps(
        local_profile_id=local_profile_id,
        profile_id=profile_id,
        db=db,
        owned_ids=owned_ids,
        limit=limit,
    )


def _recent_learning_item(
    activity: WorkspaceActivityModel,
    notebook_item: NotebookItemModel | None,
    *,
    include_content: bool = False,
) -> RecentLearningItem:
    if notebook_item is None or notebook_item.item_type != "summary":
        return RecentLearningItem(
            id=activity.id,
            knowledge_point=activity.title,
            created_at=activity.created_at,
            status="source_unavailable",
        )

    extra = notebook_item.extra_data or {}
    citations = (
        [
            Citation.model_validate(item)
            for item in extra.get("citations", [])
            if isinstance(item, dict)
        ]
        if include_content
        else []
    )
    return RecentLearningItem(
        id=activity.id,
        knowledge_point=notebook_item.knowledge_id,
        session_id=notebook_item.session_id,
        notebook_item_id=notebook_item.id,
        summary=notebook_item.content if include_content else None,
        detail=(extra.get("detail") if isinstance(extra.get("detail"), str) else None)
        if include_content
        else None,
        citations=citations,
        created_at=activity.created_at,
        status="available",
    )


@router.get("/notebook", status_code=200)
async def list_notebook_items(
    session_id: str = Query(..., min_length=1, max_length=64),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
):
    """Return notebook entries for one session or owned principals (newest first)."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    query = db.query(NotebookItemModel)
    if owned_ids:
        query = query.filter(NotebookItemModel.owner_principal_id.in_(owned_ids))
    else:
        query = query.filter(NotebookItemModel.session_id == session_id)

    items = query.order_by(NotebookItemModel.created_at.desc()).limit(50).all()
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "kind": item.item_type,
            "content": item.content,
            "timestamp": item.created_at.isoformat() if item.created_at else None,
            "source_url": (
                ((item.extra_data or {}).get("evidence_refs") or [{}])[0].get("paper_url")
                if item.item_type == "research_note"
                else None
            ),
            "research_note": (
                item.extra_data if item.item_type == "research_note" else None
            ),
            "presentation_id": (
                (item.extra_data or {}).get("presentation_id")
                if item.item_type == "presentation"
                else None
            ),
        }
        for item in items
    ]


@router.get("/presentations/{presentation_id}")
async def get_presentation(
    presentation_id: str,
    session_id: str = Query(..., min_length=1, max_length=64),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> dict:
    """Return a previously archived presentation (slides + outlines) for review."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    query = db.query(NotebookItemModel).filter(
        NotebookItemModel.item_type == "presentation",
    )
    if owned_ids:
        query = query.filter(NotebookItemModel.owner_principal_id.in_(owned_ids))
    else:
        query = query.filter(NotebookItemModel.session_id == session_id)

    items = query.all()
    item = next(
        (
            i
            for i in items
            if (i.extra_data or {}).get("presentation_id") == presentation_id
        ),
        None,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Presentation not found")

    extra = item.extra_data or {}
    return {
        "id": presentation_id,
        "knowledge_point": item.knowledge_id,
        "session_id": item.session_id,
        "style": extra.get("style", "professional"),
        "slides": extra.get("slides", []),
        "outlines": extra.get("outlines", []),
        "generation_mode": extra.get("generation_mode", "rules"),
        "provider_name": extra.get("provider_name", "mock"),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.post("/presentations/generate")
async def generate_presentation(
    request: PresentationGenerateRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> StreamingResponse:
    """Backend-driven, page-level SSE stream for knowledge-PPT generation."""
    principal_id = principal.principal_id if principal else None

    def event_source():
        for event in _presentation_generator.stream_presentation(
            request, db, owner_principal_id=principal_id
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/quiz/generate", response_model=QuizGenerateResponse, status_code=200)
async def generate_quiz(
    request: QuizGenerateRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
):
    """Generate one exercise set for a knowledge point."""
    principal_id = principal.principal_id if principal else None
    return _quiz_generator.generate(request, db, owner_principal_id=principal_id)


@router.post("/quiz/grade", response_model=GradeResponse, status_code=200)
async def grade_quiz(
    request: GradeRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> GradeResponse:
    """Grade a quiz server-side and persist every scored answer."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    principal_id = principal.principal_id if principal else None
    try:
        return _quiz_generator.grade_quiz(
            request, db, owner_principal_id=principal_id, owned_ids=owned_ids
        )
    except QuizNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/marks", response_model=MarkResponse, status_code=200)
async def set_confusion_mark(
    request: MarkRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> MarkResponse:
    """Toggle a 不懂/懂了 mark on a learning surface (PPT page / explain / quiz)."""
    principal_id = principal.principal_id if principal else None
    return _profile_service.set_mark(request, db, owner_principal_id=principal_id)


@router.get("/quiz/export-docx")
async def export_quiz_docx_endpoint(
    quiz_id: str = Query(..., min_length=1, max_length=64),
    session_id: str = Query(..., min_length=1, max_length=64),
    with_answer: bool = Query(default=False),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> Response:
    """Export a previously generated quiz as a standard Word exam paper."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        knowledge_point, questions = QuizGenerator.load_quiz(
            db, session_id, quiz_id, owned_ids=owned_ids
        )
    except QuizNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    docx_bytes = export_quiz_docx(
        knowledge_point=knowledge_point,
        questions=questions,
        with_answer=with_answer,
    )

    suffix = "（含答案）" if with_answer else ""
    fallback = f"quiz_{quiz_id[:8]}{'-answer' if with_answer else ''}.docx"
    filename = f"《{knowledge_point}》练习题{suffix}.docx"
    quoted = urllib.parse.quote(filename)
    return Response(
        content=docx_bytes,
        media_type=_DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quoted}"
            )
        },
    )

