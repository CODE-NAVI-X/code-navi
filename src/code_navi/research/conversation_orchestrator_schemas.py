"""Pydantic schemas for the Research Conversation Orchestration layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResearchStage = Literal[
    "research_need",
    "research_plan",
    "research_execution",
    "research_analysis",
]

STAGE_SEQUENCE: list[ResearchStage] = [
    "research_need",
    "research_plan",
    "research_execution",
    "research_analysis",
]

STAGE_DISPLAY_NAMES: dict[ResearchStage, str] = {
    "research_need": "研究需求确定",
    "research_plan": "研究计划生成",
    "research_execution": "研究开展",
    "research_analysis": "研究结果分析",
}

PaperUsage = Literal["replace", "compare", "cite"]


class OrchestratorSubtasks(BaseModel):
    model_config = ConfigDict(extra="ignore")

    need_defined: bool = False
    profile_ready: bool = False
    plan_generated: bool = False
    paper_selected: bool = False
    experiment_designed: bool = False
    results_analyzed: bool = False


class DirectionHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    direction: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LearnerProfileData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    domain_familiarity: str | None = None
    dev_experience: str | None = None
    projects: str | None = None
    hardware: str | None = None
    os: str | None = None
    python_env: str | None = None
    weekly_hours: str | None = None
    grade: str | None = None
    major: str | None = None


class LearnerProfileVersion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int
    profile_data: LearnerProfileData
    change_summary: str | None = None
    created_at: datetime
    is_current: bool = False


class LearnerProfileResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    current_profile: LearnerProfileData | None = None
    current_version: int | None = None
    history: list[LearnerProfileVersion] = Field(default_factory=list)


class LearnerProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    domain_familiarity: str | None = None
    dev_experience: str | None = None
    projects: str | None = None
    hardware: str | None = None
    os: str | None = None
    python_env: str | None = None
    weekly_hours: str | None = None
    grade: str | None = None
    major: str | None = None
    change_summary: str | None = None


class OrchestratorPaper(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    paper_url: str
    title: str
    purpose: PaperUsage
    is_current: bool = False
    metadata_snapshot: dict[str, object] = Field(default_factory=dict)
    selected_at: datetime


class CurrentPaperCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    paper_url: str
    title: str
    purpose: PaperUsage
    metadata_snapshot: dict[str, object] = Field(default_factory=dict)
    selected_at: datetime


class OrchestratorPapersResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    current_paper: CurrentPaperCard | None = None
    paper_history: list[OrchestratorPaper] = Field(default_factory=list)


class SelectPaperRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paper_url: str = Field(min_length=1, max_length=1000)
    title: str = Field(min_length=1, max_length=500)
    purpose: PaperUsage = "replace"
    metadata: dict[str, object] = Field(default_factory=dict)


class LearningContextInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    learned_content: str | None = None
    learning_progress: str | None = None


class LearningContextState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    learned_content: str | None = None
    learning_progress: str | None = None
    updated_at: datetime | None = None


class DirectionCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    prerequisite_gap: str | None = None
    is_recommended: bool = False


class DirectionCardsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    learned_content: str | None = None
    learning_progress: str | None = None
    cards: list[DirectionCard] = Field(default_factory=list)


class OrchestratorStateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    current_stage: ResearchStage
    completed_stages: list[ResearchStage] = Field(default_factory=list)
    subtasks: OrchestratorSubtasks
    direction_history: list[DirectionHistoryEntry] = Field(default_factory=list)
    last_status: Literal["thinking", "completed", "failed"]
    last_error: str | None = None


class SendOrchestratorMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)


class OrchestratorMessageReply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: Literal["assistant"] = "assistant"
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    passive_tool_called: str | None = None


class OrchestratorMessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str
    status: Literal["completed", "failed"]
    reply_message: OrchestratorMessageReply | None = None
    state: OrchestratorStateResponse
    error: str | None = None
