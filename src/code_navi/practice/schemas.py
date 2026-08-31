"""Pydantic schemas for the unified practice gateway (contract §1.1/§1.2/§1.3).

Field names, literals and bounds mirror
``docs/specs/hands-on-practice-research-guidance-interfaces.md`` §1 and §3.1
exactly; the contract tests fail on any drift.  Grading material
(``judge_secret``, ``CodeFillBlankSpec.answer``/``alternate_answers``) never
appears in a response model — the service strips it before building responses.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..learning.quiz.schemas import QuizAuditReport

PracticeSetKind = Literal["concept_quiz", "code_practice", "mixed"]
PracticeItemKind = Literal["concept_quiz_question", "code_fill", "coding_problem"]
JudgeChannel = Literal["rules_llm", "server_tests", "llm_static", "explain_only"]

GenerationMode = Literal["mock", "model", "rules_fallback"]
CodeFillComplexity = Literal["light", "heavy"]
CodeFillJudgeMode = Literal["llm_static", "explain_only"]
CodeFillSource = Literal["generated", "upload_derived"]

_UUID_V4_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


# ---------------------------------------------------------------------------
# §3.1 practice-context.v1 — the structured hand-off from Learning
# ---------------------------------------------------------------------------


class PracticeContextKnowledgePoint(BaseModel):
    """One knowledge point handed over from the learning flow."""

    name: str = Field(..., min_length=1, max_length=128)
    source_ref: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="notebook_item_id / explain reference from the learning side.",
    )
    mastery: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Only set when the portrait has a real value, else null.",
    )


class PracticeContextV1(BaseModel):
    """``practice-context.v1`` payload (contract §3.1)."""

    source_session_id: str = Field(..., min_length=1, max_length=64)
    knowledge_points: list[PracticeContextKnowledgePoint] = Field(
        ..., min_length=1, max_length=8
    )
    objective: str = Field(..., min_length=1, max_length=512)
    notes_summary: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# §1.1 PracticeItem envelope + CodeFillSpec
# ---------------------------------------------------------------------------


class CodeFillBlankSpec(BaseModel):
    """One blank of a code-fill item.

    ``answer`` / ``alternate_answers`` are grading material: they are stored in
    ``practice_set_items.judge_secret`` and stripped from every response.
    """

    blank_id: str = Field(..., min_length=1, max_length=64)
    answer: str = Field(..., min_length=1, max_length=500)
    alternate_answers: list[str] = Field(default_factory=list, max_length=3)
    hint: str = Field(default="", max_length=200)
    step_no: int = Field(..., ge=1)


class CodeFillStep(BaseModel):
    """One ordered build step with its architectural rationale."""

    step_no: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=120)
    reason: str = Field(
        ..., min_length=1, max_length=400, description="Why this ordering/architecture."
    )
    sub_steps: list[str] = Field(default_factory=list, max_length=4)


class CodeFillSpec(BaseModel):
    """``code_fill`` payload (contract §1.1)."""

    title: str = Field(..., min_length=1, max_length=200)
    language: Literal["python"] = "python"
    complexity: CodeFillComplexity
    judge_mode: CodeFillJudgeMode
    code_masked: str = Field(
        ...,
        min_length=1,
        max_length=16000,
        description="Code with ``______`` (6 underscores) marking each blank.",
    )
    blanks: list[CodeFillBlankSpec] = Field(..., min_length=2, max_length=6)
    steps: list[CodeFillStep] = Field(..., min_length=1, max_length=5)
    source: CodeFillSource
    reference_code_hash: str = Field(
        ..., min_length=1, description="SHA-256 of the reference code, safe to show."
    )


class PracticeItem(BaseModel):
    """Unified response unit for every practice item (contract §1.1 envelope)."""

    item_id: str = Field(..., min_length=1, description="Stable id within the set.")
    position: int = Field(..., ge=1, description="1-based position inside the set.")
    item_kind: PracticeItemKind
    knowledge_points: list[str] = Field(..., max_length=4)
    judging: JudgeChannel
    payload: dict[str, Any]
    # §1.2 note: concept items carry the grading endpoint hint so the frontend
    # knows which judge channel to call. Other kinds keep it null (additive).
    grading_hint: str | None = Field(
        default=None,
        description=(
            'concept_quiz_question → "/learning/quiz/grade"; null for other kinds.'
        ),
    )


# ---------------------------------------------------------------------------
# §1.2 generate request / response (GET §1.3 returns the same shape)
# ---------------------------------------------------------------------------


class PracticeSetGenerateRequest(BaseModel):
    """Payload for ``POST /api/v1/practice/sets/generate``."""

    kind: PracticeSetKind = "code_practice"
    count: int = Field(default=5, ge=3, le=8, description="3~8 items per set.")
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    topic: str | None = Field(
        default=None,
        max_length=512,
        description="Free topic; drives generation when no context is given.",
    )
    context: PracticeContextV1 | None = None
    profile_id: str | None = Field(
        default=None,
        pattern=_UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Optional portrait key (== practice learner_id).",
    )
    upload_ids: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="References to §1.5 upload-analysis results.",
    )
    concept_ratio: float | None = Field(
        default=None, ge=0, le=1, description="Concept share when kind=mixed."
    )


class PracticeSetResponse(BaseModel):
    """Response of the generate gateway; ``GET /sets/{set_id}`` returns the same.

    Answers never appear here: ``judge_secret`` and ``blanks[].answer`` are
    stripped by the service before this model is built.
    """

    set_id: str
    kind: PracticeSetKind
    items: list[PracticeItem]
    coverage: list[str] = Field(default_factory=list)
    generation_mode: GenerationMode
    provider_name: str
    audit: QuizAuditReport | None = None
    effective_context: PracticeContextV1 | None = None
    effective_topic: str | None = Field(
        default=None,
        description="Echoed when the topic (not a context) drove generation.",
    )


class CodeFillGradeBlankAnswer(BaseModel):
    """One student answer for one blank in a code-fill item."""

    blank_id: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., max_length=500)


class CodeFillGradeRequest(BaseModel):
    """Request for ``POST /api/v1/practice/code-fill/grade`` (contract §1.4)."""

    set_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1, max_length=64)
    attempt_id: str = Field(
        ...,
        pattern=_UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Client-minted UUID v4 idempotency key.",
    )
    blank_answers: list[CodeFillGradeBlankAnswer] = Field(..., min_length=1, max_length=6)
    profile_id: str | None = Field(
        default=None,
        pattern=_UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Optional portrait key for later aggregation.",
    )


class CodeFillGradeResultItem(BaseModel):
    """Grading fact for one blank."""

    blank_id: str
    correct: bool
    score: int
    max_score: int
    comment: str | None = None
    graded_by: Literal["rules", "model", "mock"]


class CodeFillGradeResponse(BaseModel):
    """Response for code-fill grading (contract §1.4)."""

    attempt_id: str
    item_id: str
    set_id: str
    results: list[CodeFillGradeResultItem]
    total_score: int
    total_max_score: int
    graded: bool
    is_mock: bool
    provider_name: str | None = None


class CodeUploadAnalyzeRequest(BaseModel):
    """Request for ``POST /api/v1/practice/code-uploads/analyze`` (contract §1.5)."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)


class CodeUploadSymbol(BaseModel):
    """One extracted class or function symbol."""

    kind: Literal["class", "function"]
    name: str = Field(..., min_length=1)
    line: int = Field(..., ge=1)
    signature: str = Field(default="", max_length=300)
    docstring_summary: str = Field(default="", max_length=300)


class CodeUploadAnalysisResponse(BaseModel):
    """Response for code/markdown upload analysis (contract §1.5)."""

    upload_id: str
    filename: str
    content_hash: str
    kind: Literal["python", "markdown"]
    symbols: list[CodeUploadSymbol] = Field(default_factory=list, max_length=50)
    imports: list[str] = Field(default_factory=list, max_length=30)
    framework_hints: list[str] = Field(default_factory=list, max_length=8)
    metrics: dict[str, int]
    explanation_source: Literal["rules"]


class ExplainSymbol(BaseModel):
    """A symbol to explain (contract §1.6).

    This is intentionally separate from ``CodeUploadSymbol``: explanation
    requests require ``code_excerpt`` (≤4000 chars) so the rules/model path
    never has to read an absent attribute.
    """

    name: str = Field(..., min_length=1, max_length=128)
    kind: Literal["class", "function"]
    code_excerpt: str = Field(..., max_length=4000)


class ExplainSymbolRequest(BaseModel):
    """Request for ``POST /api/v1/practice/code-fill/explain-symbol`` (contract §1.6)."""

    upload_id: str | None = Field(default=None, min_length=1, max_length=36)
    set_id: str | None = Field(default=None, min_length=1)
    item_id: str | None = Field(default=None, min_length=1, max_length=64)
    symbol: ExplainSymbol


class ExplainSymbolResponse(BaseModel):
    """Response for symbol explanation (contract §1.6)."""

    explanation: str = Field(..., max_length=600)
    source: Literal["model", "rules"]
    cached: bool


class StructureCatalogTopic(BaseModel):
    """Read-only topic summary for the static structure/framework catalogue."""

    id: str
    title: str
    description: str
    count: int


class StructureCatalogExercise(BaseModel):
    """Public summary of one static structure/framework code-fill exercise."""

    id: str
    topic_id: str
    title: str
    kind: Literal["structure_sequence", "framework_fill"]
    objective: str
    instruction: str
    options: list[str] = Field(default_factory=list)
    starter_code: str | None = None
    hints: list[str] = Field(default_factory=list)


class StructureCatalogResponse(BaseModel):
    """Read-only catalogue payload for selecting structure/framework practice."""

    schema_version: str
    topics: list[StructureCatalogTopic]
    exercises: list[StructureCatalogExercise]


__all__ = [
    "CodeFillBlankSpec",
    "CodeFillGradeBlankAnswer",
    "CodeFillGradeRequest",
    "CodeFillGradeResponse",
    "CodeFillGradeResultItem",
    "CodeFillSpec",
    "CodeFillStep",
    "CodeUploadAnalysisResponse",
    "CodeUploadAnalyzeRequest",
    "CodeUploadSymbol",
    "ExplainSymbol",
    "ExplainSymbolRequest",
    "ExplainSymbolResponse",
    "JudgeChannel",
    "PracticeContextKnowledgePoint",
    "PracticeContextV1",
    "PracticeItem",
    "PracticeItemKind",
    "PracticeSetGenerateRequest",
    "PracticeSetKind",
    "PracticeSetResponse",
    "StructureCatalogExercise",
    "StructureCatalogResponse",
    "StructureCatalogTopic",
]
