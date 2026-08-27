"""FastAPI endpoints for persisted cross-module context drafts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from code_navi.auth.dependencies import (
    CurrentPrincipal,
    get_optional_principal,
    get_owned_principal_ids,
)
from code_navi.db import get_db
from code_navi.research.conversation_schemas import ResearchConversationResponse
from code_navi.research.conversation_service import ConversationNotFoundError

from .schemas import (
    ConfirmContextTransferRequest,
    ContextTransferResponse,
    CreateContextTransferRequest,
    UpdateContextTransferRequest,
)
from .service import (
    ContextSelectionError,
    ContextTransferNotFoundError,
    ContextTransferService,
    ContextTransferStateError,
)

router = APIRouter(prefix="/api/v1/context-transfers", tags=["Context Transfer"])

_service = ContextTransferService()
_db_dependency = Depends(get_db)
_opt_principal_dep = Depends(get_optional_principal)


@router.post("", response_model=ContextTransferResponse, status_code=status.HTTP_201_CREATED)
def create_context_transfer(
    request: CreateContextTransferRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ContextTransferResponse:
    """Create a draft from a session-scoped, persisted source record."""
    principal_id = principal.principal_id if principal else None
    owned_ids = get_owned_principal_ids(principal, db) if principal else None

    try:
        return _service.create(
            request,
            db,
            owner_principal_id=principal_id,
            owned_ids=owned_ids,
        )
    except ContextTransferNotFoundError as error:
        raise HTTPException(status_code=404, detail="Learning record not found.") from error
    except ContextSelectionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{transfer_id}", response_model=ContextTransferResponse)
def get_context_transfer(
    transfer_id: str,
    source_scope_id: str = Query(..., min_length=1, max_length=64),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ContextTransferResponse:
    """Restore one draft within its source Learning session."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None

    try:
        return _service.get(transfer_id, source_scope_id, db, owned_ids=owned_ids)
    except ContextTransferNotFoundError as error:
        raise HTTPException(status_code=404, detail="Context transfer not found.") from error
    except ContextTransferStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{transfer_id}", response_model=ContextTransferResponse)
def update_context_transfer(
    transfer_id: str,
    request: UpdateContextTransferRequest,
    source_scope_id: str = Query(..., min_length=1, max_length=64),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ContextTransferResponse:
    """Edit the target-module draft while preserving its source reference."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None

    try:
        return _service.update(
            transfer_id, source_scope_id, request, db, owned_ids=owned_ids
        )
    except ContextTransferNotFoundError as error:
        raise HTTPException(status_code=404, detail="Context transfer not found.") from error
    except ContextTransferStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_context_transfer(
    transfer_id: str,
    source_scope_id: str = Query(..., min_length=1, max_length=64),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> Response:
    """Clear a draft without changing its source Learning record."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None

    try:
        _service.delete(transfer_id, source_scope_id, db, owned_ids=owned_ids)
    except ContextTransferNotFoundError as error:
        raise HTTPException(status_code=404, detail="Context transfer not found.") from error
    except ContextTransferStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{transfer_id}/confirm", response_model=ResearchConversationResponse)
def confirm_context_transfer(
    transfer_id: str,
    request: ConfirmContextTransferRequest,
    source_scope_id: str = Query(..., min_length=1, max_length=64),
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ResearchConversationResponse:
    """Atomically create a Research conversation from the editable draft."""
    principal_id = principal.principal_id if principal else None
    owned_ids = get_owned_principal_ids(principal, db) if principal else None

    try:
        return _service.confirm(
            transfer_id,
            source_scope_id,
            request,
            db,
            owner_principal_id=principal_id,
            owned_ids=owned_ids,
        )
    except ContextTransferNotFoundError as error:
        raise HTTPException(status_code=404, detail="Context transfer not found.") from error
    except (ContextTransferStateError, ConversationNotFoundError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
