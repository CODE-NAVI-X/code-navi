"""Independent API router for the learning module."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from code_navi.db import get_db

from .models import NotebookItemModel
from .presentation.schemas import PresentationGenerateRequest
from .presentation.services import PresentationGenerator
from .schemas import ExplainRequest, ExplainResponse
from .services import QueryOrchestrator

router = APIRouter(prefix="/api/v1/learning", tags=["Learning"])

_orchestrator = QueryOrchestrator()
_presentation_generator = PresentationGenerator()
_db_dependency = Depends(get_db)


@router.post("/explain", response_model=ExplainResponse, status_code=200)
async def explain_knowledge_point(
    request: ExplainRequest,
    db: Session = _db_dependency,
) -> ExplainResponse:
    """Explain a knowledge point with optional citations.

    The pipeline runs decontamination → explanation generation → notebook
    archival, all delegated to ``QueryOrchestrator``.
    """
    return _orchestrator.explain(request, db)


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
