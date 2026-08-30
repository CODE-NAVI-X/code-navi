"""API router for the unified practice gateway (contract §1).

Prefix ``/api/v1/practice``, tags ``["Practice"]``.  During the compat period
both endpoints use ``get_optional_principal`` (the same pattern as
``POST /learning/quiz/generate``): ``owner_principal_id`` stays nullable and
authenticated reads are owner-filtered — see the §0.1 ruling in the contract.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import (
    CurrentPrincipal,
    get_optional_principal,
    get_owned_principal_ids,
)
from ..db import get_db
from .schemas import PracticeSetGenerateRequest, PracticeSetResponse
from .service import (
    MissingGenerationBasis,
    PracticeSetNotFoundError,
    PracticeSetService,
)

router = APIRouter(prefix="/api/v1/practice", tags=["Practice"])

_practice_service = PracticeSetService()
_db_dependency = Depends(get_db)
_opt_principal_dep = Depends(get_optional_principal)


@router.post("/sets/generate", response_model=PracticeSetResponse, status_code=200)
async def generate_practice_set(
    request: PracticeSetGenerateRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> PracticeSetResponse:
    """Generate one practice set (S1: mock mode only, no provider call)."""
    principal_id = principal.principal_id if principal else None
    try:
        return _practice_service.generate(request, db, owner_principal_id=principal_id)
    except MissingGenerationBasis as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sets/{set_id}", response_model=PracticeSetResponse, status_code=200)
async def get_practice_set(
    set_id: str,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> PracticeSetResponse:
    """Restore an archived set (answers stripped); 404 when missing/cross-owner."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _practice_service.get_set(db, set_id, owned_ids=owned_ids)
    except PracticeSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
