"""Application service for advancing and restoring research sessions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .llm import GuidanceGenerator, GuidanceOutcome, ProviderGuidanceGenerator
from .models import ResearchSessionModel
from .rules import (
    build_brief,
    build_research_plan,
    is_complete,
    is_recommendation_request,
    missing_fields,
    next_question,
    rules_reply,
)
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
    """Rules-owned progression with optional, validated provider guidance."""

    def __init__(self, guidance_generator: GuidanceGenerator | None = None) -> None:
        self.guidance_generator = guidance_generator or ProviderGuidanceGenerator()

    def create(
        self,
        request: CreateResearchSessionRequest,
        db: Session,
    ) -> ResearchSessionResponse:
        session = ResearchSessionModel(state_data=ResearchState().model_dump(), turns_data=[])
        db.add(session)
        db.flush()
        outcome: GuidanceOutcome | None = None
        if request.initial_description and request.initial_description.strip():
            initial_description = request.initial_description.strip()
            self._record_turn(session, initial_description, "initial_description")
            target = next_question(ResearchState(**session.state_data))
            if target is not None:
                outcome = self.guidance_generator.generate(
                    state=ResearchState(**session.state_data),
                    user_reply=initial_description,
                    target_question=target,
                    requesting_suggestion=False,
                )
        db.commit()
        db.refresh(session)
        self._persist_outcome(session, outcome)
        if outcome and outcome.status in {"generated", "failed"}:
            db.commit()
            db.refresh(session)
        return self._to_response(session, outcome)

    def advance(
        self,
        session_id: str,
        request: SubmitResearchTurnRequest,
        db: Session,
    ) -> ResearchSessionResponse:
        session = self._get_model(session_id, db)
        value = (request.answer or request.selected_option or "").strip()
        input_mode = "free_text" if request.answer else "recommended_option"
        state = ResearchState(**session.state_data)
        current_question = next_question(state)
        if current_question is None:
            return self._to_response(session)
        if input_mode == "free_text" and is_recommendation_request(value):
            provisional = state.model_copy(update={current_question.field: "推荐待确认"})
            target = next_question(provisional)
            outcome = self.guidance_generator.generate(
                state=state,
                user_reply=value,
                target_question=target,
                requesting_suggestion=True,
                suggestion_question=current_question,
            )
            suggested_value = outcome.guidance.suggested_value if outcome.guidance else None
            if (
                outcome.status == "generated"
                and suggested_value
                and not is_recommendation_request(suggested_value)
            ):
                self._record_turn(session, suggested_value.strip(), "llm_suggested")
                db.commit()
                db.refresh(session)
                self._persist_outcome(session, outcome)
                db.commit()
                db.refresh(session)
                return self._to_response(session, outcome)
            if outcome.status == "failed" or suggested_value:
                fallback = GuidanceOutcome.failed("model suggestion did not fill the current field")
                self._persist_outcome(session, fallback)
                db.commit()
                db.refresh(session)
                return self._to_response(session, fallback)
            # An unavailable model (including no API key), or a response without a
            # usable suggestion, must leave the field empty and keep the deterministic
            # question rather than persisting the user's uncertainty as research data.
            return self._to_response(session)
        self._record_turn(session, value, input_mode)
        db.commit()
        db.refresh(session)
        state_after = ResearchState(**session.state_data)
        target = next_question(state_after)
        if target is None:
            return self._to_response(session)
        outcome = self.guidance_generator.generate(
            state=state_after,
            user_reply=value,
            target_question=target,
            requesting_suggestion=False,
        )
        self._persist_outcome(session, outcome)
        if outcome.status in {"generated", "failed"}:
            db.commit()
            db.refresh(session)
        return self._to_response(session, outcome)

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

    @staticmethod
    def _persist_outcome(
        session: ResearchSessionModel,
        outcome: GuidanceOutcome | None,
    ) -> None:
        """Persist a non-sensitive display result beside its triggering user turn."""
        if not (outcome and outcome.status in {"generated", "failed"} and session.turns_data):
            return
        last_turn = dict(session.turns_data[-1])
        last_turn["guidance_status"] = outcome.status
        if outcome.status == "generated" and outcome.guidance:
            last_turn["guidance"] = outcome.guidance.model_dump()
        session.turns_data = [*session.turns_data[:-1], last_turn]

    @staticmethod
    def _persisted_outcome(session: ResearchSessionModel) -> GuidanceOutcome | None:
        """Restore prior display state without re-calling a provider on GET."""
        if not session.turns_data:
            return None
        last_turn = session.turns_data[-1]
        if last_turn.get("guidance_status") == "failed":
            return GuidanceOutcome.failed("previous guidance call failed")
        raw_guidance = last_turn.get("guidance")
        if not isinstance(raw_guidance, dict):
            return None
        try:
            from .llm import LlmGuidance

            return GuidanceOutcome.generated(LlmGuidance.model_validate(raw_guidance))
        except ValueError:
            return None

    def _to_response(
        self,
        session: ResearchSessionModel,
        outcome: GuidanceOutcome | None = None,
    ) -> ResearchSessionResponse:
        state = ResearchState(**session.state_data)
        question = next_question(state)
        if outcome is None:
            outcome = self._persisted_outcome(session)
        mode = "rules"
        reply = rules_reply(question)
        if outcome and outcome.status == "generated" and outcome.guidance:
            guidance = outcome.guidance
            if question is not None:
                question = question.model_copy(
                    update={"question": guidance.next_question.strip(), "options": guidance.options}
                )
            reply = guidance.reply.strip()
            mode = "llm"
        elif outcome and outcome.status == "failed":
            mode = "rules_fallback"
        return ResearchSessionResponse(
            session_id=session.id,
            state=state,
            missing_fields=missing_fields(state),
            next_question=question,
            completed=is_complete(state),
            reply=reply,
            generation_mode=mode,
            research_brief=build_brief(state),
            research_plan=build_research_plan(state),
            turns=[ResearchTurn(**turn) for turn in session.turns_data],
        )
