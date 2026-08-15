"""Independent API router for the learning portrait.

The portrait endpoint is deliberately **not** session-scoped — it aggregates
across all sessions sharing one ``profile_id``.  Single-item detail reads stay
session-scoped in their own modules (CLAUDE.md rule 10); this module owns the
cross-session aggregation boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from code_navi.db import get_db

from .schemas import UUID_V4_PATTERN, ProfileResponse
from .service import ProfileService

router = APIRouter(prefix="/api/v1/profile", tags=["Profile"])

_profile_service = ProfileService()
_db_dependency = Depends(get_db)


@router.get("", response_model=ProfileResponse, status_code=200)
async def get_profile(
    profile_id: str = Query(
        ...,
        pattern=UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Unified profile key (UUID v4, == the practice learner_id).",
    ),
    db: Session = _db_dependency,
) -> ProfileResponse:
    """Return the anonymous learning portrait for one profile key.

    Same semantics as ``GET /api/v1/compiler/records``: no authentication —
    the caller reads only what it knows the key for, this is not an
    authorization query.  An unknown key yields an empty portrait (200 with
    ``sample_size=0``), never 404, so a client cannot probe key existence.
    """
    return _profile_service.get_profile(profile_id, db)
