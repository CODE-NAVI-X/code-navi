"""Public request and response schemas for research clarification."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ResearchState(BaseModel):
    """The five fixed fields that must be collected before completion."""

    research_domain: str | None = None
    core_question: str | None = None
    data_and_method: str | None = None
    constraints: str | None = None
    expected_deliverable: str | None = None


class ResearchBrief(ResearchState):
    """Completed, structured research brief produced only by rules."""


class ClarificationQuestion(BaseModel):
    """One deterministic question and its three recommended responses."""

    field: str
    label: str
    question: str
    options: list[str] = Field(min_length=3, max_length=3)


class ResearchTurn(BaseModel):
    """Persisted user response used to make a session auditable and resumable."""

    field: str
    value: str
    input_mode: str
    recorded_at: datetime


class CreateResearchSessionRequest(BaseModel):
    """Optional initial description, treated as the first free-text response."""

    initial_description: str | None = Field(default=None, max_length=500)


class SubmitResearchTurnRequest(BaseModel):
    """A user may choose one recommended option or provide free text."""

    answer: str | None = Field(default=None, max_length=500)
    selected_option: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_exactly_one_response(self) -> SubmitResearchTurnRequest:
        values = [value for value in (self.answer, self.selected_option) if value and value.strip()]
        if len(values) != 1:
            raise ValueError("Provide exactly one of answer or selected_option.")
        return self


class ResearchSessionResponse(BaseModel):
    """Stable API response for creation, progression, and restoration."""

    session_id: str
    state: ResearchState
    missing_fields: list[str]
    next_question: ClarificationQuestion | None
    completed: bool
    research_brief: ResearchBrief | None = None
    turns: list[ResearchTurn]
