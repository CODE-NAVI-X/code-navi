"""Independent API router for the learning module."""

from __future__ import annotations

import json
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

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

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.post("/explain", response_model=ExplainResponse, status_code=200)
async def explain_knowledge_point(
    request: ExplainRequest,
    db: Session = _db_dependency,
) -> ExplainResponse:
    """Explain a knowledge point with optional citations.

    The pipeline runs decontamination → explanation generation → notebook
    archival, all delegated to ``QueryOrchestrator``.
    """
    try:
        if request.local_profile_id is None:
            return _orchestrator.explain(request, db)

        context = _workspace_service.resolve_learning_context(
            local_profile_id=request.local_profile_id,
            workspace_id=request.workspace_id,
            task_id=request.task_id,
            db=db,
        )
        return _orchestrator.explain(
            request,
            db,
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
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(4, ge=1, le=12),
    db: Session = _db_dependency,
) -> RecentLearningListResponse:
    """Return a small, recoverable Learning history for the current local profile.

    Activities are only an index.  The response carries the persisted notebook
    source required to restore the explanation, and explicitly labels stale
    indices when that source is no longer available.
    """
    rows = (
        db.query(WorkspaceActivityModel, NotebookItemModel)
        .join(WorkspaceModel, WorkspaceActivityModel.workspace_id == WorkspaceModel.id)
        .outerjoin(
            NotebookItemModel,
            NotebookItemModel.id == WorkspaceActivityModel.source_object_id,
        )
        .filter(
            WorkspaceModel.owner_scope_id == local_profile_id,
            WorkspaceActivityModel.capability == "learning",
            WorkspaceActivityModel.action_type == "knowledge_explained",
            WorkspaceActivityModel.source_object_type == "notebook_item",
        )
        .order_by(WorkspaceActivityModel.created_at.desc(), WorkspaceActivityModel.id.desc())
        .limit(limit)
        .all()
    )
    return RecentLearningListResponse(
        items=[_recent_learning_item(activity, notebook_item) for activity, notebook_item in rows]
    )


@router.get("/recent/{activity_id}", response_model=RecentLearningItem)
async def get_recent_learning(
    activity_id: str,
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    db: Session = _db_dependency,
) -> RecentLearningItem:
    """Load one persisted Learning source after a user chooses to restore it."""
    row = (
        db.query(WorkspaceActivityModel, NotebookItemModel)
        .join(WorkspaceModel, WorkspaceActivityModel.workspace_id == WorkspaceModel.id)
        .outerjoin(
            NotebookItemModel,
            NotebookItemModel.id == WorkspaceActivityModel.source_object_id,
        )
        .filter(
            WorkspaceActivityModel.id == activity_id,
            WorkspaceModel.owner_scope_id == local_profile_id,
            WorkspaceActivityModel.capability == "learning",
            WorkspaceActivityModel.action_type == "knowledge_explained",
            WorkspaceActivityModel.source_object_type == "notebook_item",
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Recent Learning item not found.")
    return _recent_learning_item(*row, include_content=True)


@router.get("/knowledge-gaps", response_model=KnowledgeGapResponse)
async def list_knowledge_gaps(
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    profile_id: str = Query(
        ...,
        pattern=UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Unified anonymous learner/profile UUID used by Learning and Practice.",
    ),
    limit: int = Query(50, ge=1, le=100),
    db: Session = _db_dependency,
) -> KnowledgeGapResponse:
    """Return traceable review items for the current local Learning portrait.

    This is a read projection only. QuizAttempt and ConfusionMark facts are
    selected by the caller's anonymous ``profile_id``; PracticeOutcome facts are
    additionally scoped by ``local_profile_id`` because they belong to the
    Workspace owner boundary. The endpoint does not create a KnowledgeGap table
    or imply account-level authorization.
    """
    return _profile_service.get_knowledge_gaps(
        local_profile_id=local_profile_id,
        profile_id=profile_id,
        db=db,
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
    db: Session = _db_dependency,
):
    """Return notebook entries for one session (newest first).

    ``session_id`` is required and actually scopes the query — without it a
    client would read every session's entries.
    """
    items = (
        db.query(NotebookItemModel)
        .filter(
            NotebookItemModel.user_id == "poc-user",
            NotebookItemModel.session_id == session_id,
        )
        .order_by(NotebookItemModel.created_at.desc())
        .limit(50)
        .all()
    )
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
            # Presentation items carry their deck id so the client can re-fetch
            # the full slides for review without pulling every deck in the list.
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
    db: Session = _db_dependency,
) -> dict:
    """Return a previously archived presentation (slides + outlines) for review.

    ``session_id`` is required and scopes the lookup to the requesting
    session, matching the notebook list endpoint — without it a client would
    read any session's deck by id.
    """
    from fastapi import HTTPException

    items = (
        db.query(NotebookItemModel)
        .filter(
            NotebookItemModel.user_id == "poc-user",
            NotebookItemModel.session_id == session_id,
            NotebookItemModel.item_type == "presentation",
        )
        .all()
    )
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
    db: Session = _db_dependency,
) -> StreamingResponse:
    """Backend-driven, page-level SSE stream for knowledge-PPT generation.

    Emits events as pages finish (``outlines`` → ``slide`` × N → ``done``), so
    the client can render page N while page N+1 is still being generated.  The
    generator is synchronous and runs in FastAPI's thread pool; each page costs
    one audited kernel run, matching the learning module's Event/audit contract.
    """

    def event_source():
        for event in _presentation_generator.stream_presentation(request, db):
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
    db: Session = _db_dependency,
):
    """Generate one exercise set for a knowledge point.

    Runs one audited kernel call (no tools granted), normalizes the LLM JSON
    array into the shared question model, and archives the quiz to the student
    notebook under the effective ``session_id``.
    """
    return _quiz_generator.generate(request, db)


@router.post("/quiz/grade", response_model=GradeResponse, status_code=200)
async def grade_quiz(
    request: GradeRequest,
    db: Session = _db_dependency,
) -> GradeResponse:
    """Grade a quiz server-side and persist every scored answer.

    The scoring rubric is loaded from the archived quiz strictly within the
    requesting ``session_id`` — the client submits only the quiz id and the
    student's answers, so it cannot alter the correct answers or points.
    ``single`` is graded deterministically server-side (``graded_by=rules``);
    ``fill_blank`` / ``short_answer`` go through the LLM when an online
    provider is configured.  Offline degrades honestly (exact match for fill
    blanks, ``graded=false`` + self-check hint for short answers) and never
    fakes an LLM verdict.  All results are persisted as ``quiz_attempts``.
    """
    try:
        return _quiz_generator.grade_quiz(request, db)
    except QuizNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/marks", response_model=MarkResponse, status_code=200)
async def set_confusion_mark(
    request: MarkRequest,
    db: Session = _db_dependency,
) -> MarkResponse:
    """Toggle a 不懂/懂了 mark on a learning surface (PPT page / explain / quiz).

    Writes are scoped to ``session_id``; the optional ``profile_id`` lets the
    mark aggregate into the cross-session portrait.  The toggle is idempotent
    on ``(session_id, source_type, source_ref)``.
    """
    return _profile_service.set_mark(request, db)


@router.get("/quiz/export-docx")
async def export_quiz_docx_endpoint(
    quiz_id: str = Query(..., min_length=1, max_length=64),
    session_id: str = Query(..., min_length=1, max_length=64),
    with_answer: bool = Query(default=False),
    db: Session = _db_dependency,
) -> Response:
    """Export a previously generated quiz as a standard Word exam paper.

    The quiz is looked up strictly within the requesting ``session_id`` — a
    quiz id that belongs to another session yields 404, matching the notebook
    list / presentation read-back behavior.  ``with_answer`` appends a
    参考答案 section at the end of the same document.
    """
    try:
        knowledge_point, questions = QuizGenerator.load_quiz(db, session_id, quiz_id)
    except QuizNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    docx_bytes = export_quiz_docx(
        knowledge_point=knowledge_point,
        questions=questions,
        with_answer=with_answer,
    )

    suffix = "（含答案）" if with_answer else ""
    # ``filename`` must stay ASCII (RFC 5987); the readable Chinese name goes
    # into ``filename*`` only.
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
