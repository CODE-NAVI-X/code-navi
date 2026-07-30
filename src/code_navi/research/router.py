"""FastAPI router for the rules-driven research-clarification workflow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from code_navi.learning.database import get_db

from .schemas import (
    CreateResearchSessionRequest,
    ResearchSessionResponse,
    SubmitResearchTurnRequest,
)
from .service import ResearchClarificationService, ResearchSessionNotFoundError

router = APIRouter(prefix="/api/v1/research", tags=["Research"])
_service = ResearchClarificationService()
_db_dependency = Depends(get_db)


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
