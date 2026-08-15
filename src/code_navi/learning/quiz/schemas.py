"""Pydantic request / response data-models for the learning quiz feature.

The question model is deliberately aligned with OpenMAIC's ``QuizQuestion``
(``lib/types/stage.ts``) so the frontend can reuse its existing quiz renderer,
grading helpers and prompt-derived JSON shapes.  Two extensions are added on
top of the OpenMAIC port:

- ``fill_blank`` — a new question type with one ``answer`` entry per ``______``
  blank inside the stem.
- LaTeX math — ``question`` / option labels may embed ``$...$`` inline math,
  which the docx exporter converts to native Word equations (OMML).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["single", "fill_blank", "short_answer"]

Difficulty = Literal["easy", "medium", "hard"]

#: How a question was obtained. ``local_bank`` is defined up-front so a future
#: local question bank / knowledge base can select & compose papers from it.
SourceType = Literal["generated", "web", "local_bank"]

SourceMode = Literal["generated", "web"]


class QuizQuestionSource(BaseModel):
    """Provenance of one question, shown to the student in the UI."""

    type: SourceType = Field(
        default="generated", description="generated | web | local_bank."
    )
    label: str = Field(
        default="AI 生成",
        description=(
            "Human-readable source, e.g. '来自学科知识库改编', '改编自 <domain>', "
            "'AI 生成'. The frontend renders this as a small badge."
        ),
    )
    uri: str | None = Field(
        default=None, description="Resolvable URL of the original material, if any."
    )
    accessed_at: datetime | None = Field(
        default=None, description="When the web material was retrieved, if any."
    )


class QuizOption(BaseModel):
    """One answer option of a choice question."""

    label: str = Field(..., description="Display text; may contain $...$ LaTeX math.")
    value: str = Field(..., description="Selection key, e.g. 'A', 'B', 'C', 'D'.")


class QuizQuestion(BaseModel):
    """A single generated exercise."""

    id: str = Field(..., description="Stable question id within one quiz.")
    type: QuestionType = Field(..., description="single | fill_blank | short_answer")
    question: str = Field(..., description="Stem; may embed $...$ LaTeX math.")
    options: list[QuizOption] | None = Field(
        default=None, description="Present for ``single``; absent for the other types."
    )
    answer: list[str] | None = Field(
        default=None,
        description=(
            "single: one option value e.g. ['A']. fill_blank: one entry per blank, "
            "in order. short_answer: null (graded by an LLM / reference answer)."
        ),
    )
    analysis: str | None = Field(
        default=None, description="Explanation shown after grading."
    )
    points: int = Field(default=10, ge=1, le=100, description="Score assigned to this item.")
    comment_prompt: str | None = Field(
        default=None,
        description="Grading rubric used by LLM judges for ``short_answer``.",
    )
    source: QuizQuestionSource = Field(
        default_factory=QuizQuestionSource,
        description="Where this question came from (AI / web adaptation / future bank).",
    )


class QuizAuditScore(BaseModel):
    """One scored dimension of the post-generation audit."""

    dimension: Literal["difficulty_fit", "coverage", "quality"] = Field(
        ..., description="difficulty_fit | coverage | quality."
    )
    score: int = Field(..., ge=0, le=10, description="Score out of 10.")
    note: str = Field(default="", description="Short justification.")


class QuizAuditReport(BaseModel):
    """Model verdict on the composed paper, used to gate auto-revision."""

    verdict: Literal["pass", "adjust"] = Field(
        ..., description="pass: ship as-is; adjust: a revision round should run."
    )
    scores: list[QuizAuditScore] = Field(
        default_factory=list, description="Per-dimension scores."
    )
    notes: list[str] = Field(default_factory=list, description="Actionable audit notes.")
    revised: bool = Field(
        default=False, description="True when an adjustment round already re-ran."
    )
    revision_summary: str | None = Field(
        default=None, description="What the revision round changed, if any."
    )


class QuizGenerateRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/quiz/generate``."""

    knowledge_point: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="The knowledge-point identifier or free-text topic to exercise.",
    )
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Client-owned learning session. Omit to have the server mint one; "
            "the returned value scopes later quiz reads / docx export."
        ),
    )
    question_count: int = Field(
        default=5, ge=1, le=30, description="Total number of questions to generate."
    )
    question_types: list[QuestionType] | None = Field(
        default=None,
        description=(
            "Types to include, e.g. ['single', 'fill_blank']. Defaults to all three "
            "if omitted."
        ),
    )
    difficulty: Difficulty = Field(
        default="medium", description="easy | medium | hard."
    )
    with_latex: bool = Field(
        default=True,
        description=(
            "Whether the prompt may use $...$ LaTeX math in stems/options. The "
            "docx exporter always renders any LaTeX found as native Word equations."
        ),
    )
    source_mode: SourceMode = Field(
        default="generated",
        description=(
            "generated: pure LLM generation. web: ground generation on web-retrieved "
            "material (Tavily when TAVILY_API_KEY is set; graceful fallback to "
            "generated otherwise) and tag each question with its source."
        ),
    )
    student_profile: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "Free-text 学情 context — persona, weak points, mastery hints, preferred "
            "difficulty. The model adapts question difficulty and content to it."
        ),
    )


class QuizGenerateResponse(BaseModel):
    """Response returned after generating one exercise set."""

    knowledge_point: str = Field(..., description="Echoed topic from the request.")
    session_id: str = Field(
        ..., description="Effective session; persist it to scope later quiz reads."
    )
    quiz_id: str = Field(..., description="Opaque id addressing this quiz for export.")
    questions: list[QuizQuestion] = Field(..., description="Generated questions.")
    generation_mode: str = Field(
        ..., description="mock | model | rules_fallback — how the payload was produced."
    )
    provider_name: str = Field(
        ..., description="Provider that produced the payload (mock | deepseek | ...)."
    )
    source_mode: SourceMode = Field(
        default="generated",
        description="Echo of the effective source mode after fallback.",
    )
    total_points: int = Field(..., description="Sum of question points for display.")
    audit: QuizAuditReport | None = Field(
        default=None, description="Post-generation model audit of the paper."
    )


class StudentAnswerItem(BaseModel):
    """One student's answer to a single / fill_blank / short_answer item."""

    question_id: str = Field(
        ..., description="Must match an id in the archived quiz being graded."
    )
    answer: list[str] = Field(
        default_factory=list,
        description=(
            "single: the selected option value e.g. ['B']. fill_blank: one entry "
            "per blank, in order. short_answer: a single entry holding the "
            "free-text answer."
        ),
    )


#: UUID v4 (the learner profile id format) — enforces the client-minted
#: idempotency key and the unified portrait aggregation key at the API edge.
_UUID_V4_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


class GradeRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/quiz/grade``.

    The client submits only the quiz id and the student's answers — the grading
    rubric (correct answers, points, ``comment_prompt``) is loaded server-side
    from the archived quiz, so a caller cannot alter the scoring basis.
    ``attempt_id`` is a client-minted UUID v4 idempotency key: a retried request
    re-uses it and the server upserts rather than double-inserts.  ``profile_id``
    (== the practice ``learner_id`` UUID) is optional and keys the cross-session
    learning portrait.
    """

    session_id: str = Field(
        ..., min_length=1, max_length=64, description="Scopes the archived quiz lookup."
    )
    quiz_id: str = Field(
        ..., min_length=1, max_length=64, description="The archived quiz to grade."
    )
    attempt_id: str = Field(
        ...,
        pattern=_UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description="Client-minted UUID v4 idempotency key for this submission.",
    )
    profile_id: str | None = Field(
        default=None,
        pattern=_UUID_V4_PATTERN,
        min_length=36,
        max_length=36,
        description=(
            "Optional unified profile key (== the practice learner_id UUID). "
            "When present, this attempt is aggregated into the learning portrait."
        ),
    )
    student_answers: list[StudentAnswerItem] = Field(
        default_factory=list,
        description="The student's answers, one entry per answered question.",
    )


class QuestionGradeResult(BaseModel):
    """One graded question: score plus an LLM comment or a mock fallback marker."""

    question_id: str = Field(..., description="Question id this grade refers to.")
    type: QuestionType = Field(
        ..., description="single | fill_blank | short_answer."
    )
    score: int = Field(..., ge=0, description="Awarded points, clamped to 0..max_score.")
    max_score: int = Field(..., ge=1, description="Full points for this item.")
    is_correct: bool = Field(
        ..., description="True when full points were awarded (score >= max_score)."
    )
    comment: str | None = Field(
        default=None, description="Chinese grading analysis / suggestion from the LLM."
    )
    is_mock: bool = Field(
        default=False,
        description=(
            "True when this is deterministic offline grading, not a real LLM "
            "judgment — the UI must label it 离线 Mock 判分, never a model verdict."
        ),
    )
    graded: bool = Field(
        default=True,
        description=(
            "False only when offline mode cannot grade a short answer; the UI "
            "then prompts self-grading against the reference answer."
        ),
    )
    graded_by: Literal["mock", "rules", "model"] = Field(
        default="rules",
        description=(
            "How this score was produced: rules (deterministic single-choice "
            "comparison), mock (offline deterministic fill-blank comparison), or "
            "model (LLM judgment).  Drives the portrait's fact boundary."
        ),
    )


class GradeResponse(BaseModel):
    """Response of the grading endpoint."""

    session_id: str = Field(..., description="Echoed from the request.")
    attempt_id: str = Field(
        ..., description="Echoed idempotency key; addresses the persisted attempts."
    )
    results: list[QuestionGradeResult] = Field(
        default_factory=list, description="One result per graded question."
    )
    generation_mode: str = Field(
        ..., description="mock | model | rules_fallback — how the results were produced."
    )
    provider_name: str = Field(
        ..., description="Provider that produced the grades (mock | deepseek | ...)."
    )
    total_score: int = Field(
        ..., ge=0, description="Sum of awarded scores across graded results."
    )
    total_max_score: int = Field(
        ..., ge=0, description="Sum of max scores across graded results."
    )
