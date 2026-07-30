"""Application service for advancing and restoring research sessions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .models import ResearchSessionModel
from .rules import build_brief, build_research_plan, is_complete, missing_fields, next_question
from .schemas import (
    CreateResearchSessionRequest,
    ResearchSessionResponse,
    ResearchState,
    ResearchTurn,
    SubmitResearchTurnRequest,
)


class ResearchSessionNotFoundError(LookupError):
    """Raised when a requested application-owned research session is absent."""


class ResearchClarificationService:
    """Rules-only state progression with SQLite persistence and no model calls."""

    def create(
        self,
        request: CreateResearchSessionRequest,
        db: Session,
    ) -> ResearchSessionResponse:
        session = ResearchSessionModel(state_data=ResearchState().model_dump(), turns_data=[])
        db.add(session)
        db.flush()
        if request.initial_description and request.initial_description.strip():
            self._record_turn(
                session,
                request.initial_description.strip(),
                "initial_description",
            )
        db.commit()
        db.refresh(session)
        return self._to_response(session)

    def advance(
        self,
        session_id: str,
        request: SubmitResearchTurnRequest,
        db: Session,
    ) -> ResearchSessionResponse:
        session = self._get_model(session_id, db)
        value = (request.answer or request.selected_option or "").strip()
        input_mode = "free_text" if request.answer else "recommended_option"
        self._record_turn(session, value, input_mode)
        db.commit()
        db.refresh(session)
        return self._to_response(session)

    def get(self, session_id: str, db: Session) -> ResearchSessionResponse:
        return self._to_response(self._get_model(session_id, db))

    def _get_model(self, session_id: str, db: Session) -> ResearchSessionModel:
        session = db.get(ResearchSessionModel, session_id)
        if session is None:
            raise ResearchSessionNotFoundError(session_id)
        return session

    def _record_turn(self, session: ResearchSessionModel, value: str, input_mode: str) -> None:
        state = ResearchState(**session.state_data)
        question = next_question(state)
        if question is None:
            return
        updated_state = state.model_copy(update={question.field: value})
        record = ResearchTurn(
            field=question.field,
            value=value,
            input_mode=input_mode,
            recorded_at=datetime.now(UTC),
        )
        session.state_data = updated_state.model_dump()
        session.turns_data = [*session.turns_data, record.model_dump(mode="json")]

    def _to_response(self, session: ResearchSessionModel) -> ResearchSessionResponse:
        state = ResearchState(**session.state_data)
        return ResearchSessionResponse(
            session_id=session.id,
            state=state,
            missing_fields=missing_fields(state),
            next_question=next_question(state),
            completed=is_complete(state),
            research_brief=build_brief(state),
            research_plan=build_research_plan(state),
            turns=[ResearchTurn(**turn) for turn in session.turns_data],
        )
