"""FastAPI router for unified portraits overview read endpoint (contract §4.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from code_navi.auth.dependencies import (
    CurrentPrincipal,
    get_optional_principal,
    get_owned_principal_ids,
)
from code_navi.db import get_db
from code_navi.learning_profile.schemas import UUID_V4_PATTERN

from .schemas import PortraitsOverviewResponse
from .service import PortraitsOverviewService

router = APIRouter(prefix="/api/v1/portraits", tags=["Portraits"])

_overview_service = PortraitsOverviewService()
_db_dependency = Depends(get_db)
_opt_principal_dep = Depends(get_optional_principal)


@router.get(
    "/overview",
    response_model=PortraitsOverviewResponse,
    status_code=status.HTTP_200_OK,
)
def get_portraits_overview(
    profile_id: str = Query(
        ...,
        pattern=UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Unified profile key (UUID v4, == the practice learner_id).",
    ),
    local_profile_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Optional local practice profile key. The browser mints a "
            "`profile-`-prefixed id (not a UUID); the Practice review "
            "projection keys on it verbatim."
        ),
    ),
    conversation_limit: int = Query(
        default=5,
        ge=1,
        le=10,
        description="Max research conversations to return (1..10).",
    ),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> PortraitsOverviewResponse:
    """Return the unified learning and research portrait overview (contract §4.1)."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    return _overview_service.get_overview(
        profile_id=profile_id,
        local_profile_id=local_profile_id,
        conversation_limit=conversation_limit,
        db=db,
        owned_ids=owned_ids,
    )


__all__ = ["router"]
