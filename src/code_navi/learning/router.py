"""Independent API router for the learning module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from code_navi.db import get_db

from .models import NotebookItemModel
from .schemas import ExplainRequest, ExplainResponse
from .services import QueryOrchestrator

router = APIRouter(prefix="/api/v1/learning", tags=["Learning"])

_orchestrator = QueryOrchestrator()
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
            "source_url": None,
        }
        for item in items
    ]
