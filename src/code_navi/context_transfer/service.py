"""Application rules for creating and editing cross-module context drafts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from code_navi.learning.models import NotebookItemModel
from code_navi.research.conversation_schemas import ResearchConversationResponse
from code_navi.research.conversation_service import ResearchConversationService

from .models import ContextTransferModel
from .schemas import (
    ConfirmContextTransferRequest,
    ConfirmedContextProvenance,
    ContextSourceObject,
    ContextTransferResponse,
    CreateContextTransferRequest,
    SelectedContextContent,
    UpdateContextTransferRequest,
)


class ContextTransferNotFoundError(LookupError):
    """The transfer or its session-scoped source record does not exist."""


class ContextSelectionError(ValueError):
    """The requested source content is not available for transfer."""


class ContextTransferStateError(RuntimeError):
    """The requested draft mutation conflicts with its confirmed state."""


class ContextTransferService:
    """Create drafts from canonical source records and keep snapshots editable."""

    def __init__(self, research_service: ResearchConversationService | None = None) -> None:
        self.research_service = research_service or ResearchConversationService()

    def create(
        self,
        request: CreateContextTransferRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> ContextTransferResponse:
        query = db.query(NotebookItemModel).filter(
            NotebookItemModel.id == request.source_object.id,
        )
        if owned_ids:
            query = query.filter(NotebookItemModel.owner_principal_id.in_(owned_ids))
        else:
            query = query.filter(NotebookItemModel.session_id == request.source_scope_id)
        source = query.first()
        if source is None:
            raise ContextTransferNotFoundError(request.source_object.id)

        selected_content = self._selected_content(source, request.selected_parts)
        transfer = ContextTransferModel(
            owner_principal_id=owner_principal_id,
            source_module=request.source_module,
            source_object_type=request.source_object.type,
            source_object_id=source.id,
            source_scope_id=source.session_id,
            target_module=request.target_module,
            topic=source.knowledge_id,
            summary=source.content,
            selected_content=[item.model_dump(mode="json") for item in selected_content],
        )
        db.add(transfer)
        db.commit()
        db.refresh(transfer)
        return self._response(transfer)

    def get(
        self,
        transfer_id: str,
        source_scope_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ContextTransferResponse:
        return self._response(
            self._get_model(transfer_id, source_scope_id, db, owned_ids=owned_ids)
        )

    def update(
        self,
        transfer_id: str,
        source_scope_id: str,
        request: UpdateContextTransferRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ContextTransferResponse:
        transfer = self._get_model(transfer_id, source_scope_id, db, owned_ids=owned_ids)
        self._require_draft(transfer)
        changes = request.model_dump(exclude_unset=True)
        if "topic" in changes:
            transfer.topic = changes["topic"]
        if "summary" in changes:
            transfer.summary = changes["summary"]
        if "selected_content" in changes:
            transfer.selected_content = [
                item.model_dump(mode="json") for item in request.selected_content or []
            ]
        db.commit()
        db.refresh(transfer)
        return self._response(transfer)

    def delete(
        self,
        transfer_id: str,
        source_scope_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> None:
        transfer = self._get_model(transfer_id, source_scope_id, db, owned_ids=owned_ids)
        self._require_draft(transfer)
        db.delete(transfer)
        db.commit()

    def confirm(
        self,
        transfer_id: str,
        source_scope_id: str,
        request: ConfirmContextTransferRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> ResearchConversationResponse:
        """Atomically persist the final snapshot and create its Research conversation."""
        transfer = self._get_model(transfer_id, source_scope_id, db, owned_ids=owned_ids)
        if transfer.status == "confirmed":
            if not transfer.confirmed_conversation_id:
                raise ContextTransferStateError("Confirmed context has no conversation.")
            return self.research_service.get(transfer.confirmed_conversation_id, db)

        confirmed_at = datetime.now(UTC)
        provenance = ConfirmedContextProvenance(
            transfer_id=transfer.id,
            source_module=transfer.source_module,
            source_object=ContextSourceObject(
                type=transfer.source_object_type,
                id=transfer.source_object_id,
            ),
            source_scope_id=transfer.source_scope_id,
            target_module=transfer.target_module,
            topic=request.topic,
            summary=request.summary,
            selected_content=request.selected_content,
            confirmed_at=confirmed_at,
        )
        try:
            conversation = self.research_service.create_from_confirmed_context(
                provenance,
                db,
                owner_principal_id=owner_principal_id or transfer.owner_principal_id,
                commit=False,
            )
            transfer.topic = request.topic
            transfer.summary = request.summary
            transfer.selected_content = [
                item.model_dump(mode="json") for item in request.selected_content
            ]
            transfer.status = "confirmed"
            transfer.confirmed_conversation_id = conversation.conversation_id
            transfer.confirmed_at = confirmed_at
            db.commit()
        except Exception:
            db.rollback()
            raise
        return conversation

    @staticmethod
    def _get_model(
        transfer_id: str,
        source_scope_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ContextTransferModel:
        query = db.query(ContextTransferModel).filter(
            ContextTransferModel.id == transfer_id,
        )
        if owned_ids:
            query = query.filter(ContextTransferModel.owner_principal_id.in_(owned_ids))
        else:
            query = query.filter(ContextTransferModel.source_scope_id == source_scope_id)
        transfer = query.first()
        if transfer is None:
            raise ContextTransferNotFoundError(transfer_id)
        return transfer

    @staticmethod
    def _selected_content(
        source: NotebookItemModel,
        selected_parts: list[str],
    ) -> list[SelectedContextContent]:
        extra = source.extra_data or {}
        available = {
            "summary": SelectedContextContent(
                kind="summary",
                label="学习摘要",
                content=source.content,
            ),
        }
        detail = extra.get("detail")
        if isinstance(detail, str) and detail.strip():
            available["detail"] = SelectedContextContent(
                kind="detail",
                label="详细讲解",
                content=detail,
            )
        missing = [part for part in selected_parts if part not in available]
        if missing:
            raise ContextSelectionError(f"source content is unavailable: {', '.join(missing)}")
        return [available[part] for part in selected_parts]

    @staticmethod
    def _require_draft(transfer: ContextTransferModel) -> None:
        if transfer.status != "draft":
            raise ContextTransferStateError("Confirmed context cannot be changed or cancelled.")

    @staticmethod
    def _response(transfer: ContextTransferModel) -> ContextTransferResponse:
        return ContextTransferResponse(
            id=transfer.id,
            source_module=transfer.source_module,
            source_object=ContextSourceObject(
                type=transfer.source_object_type,
                id=transfer.source_object_id,
            ),
            source_scope_id=transfer.source_scope_id,
            target_module=transfer.target_module,
            topic=transfer.topic,
            summary=transfer.summary,
            selected_content=transfer.selected_content,
            status=transfer.status,
            confirmed_conversation_id=transfer.confirmed_conversation_id,
            confirmed_at=transfer.confirmed_at,
            created_at=transfer.created_at,
            updated_at=transfer.updated_at,
        )
