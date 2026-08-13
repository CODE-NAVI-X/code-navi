"""Quiz generation service.

Pipeline per request: generate → audit → (optionally) revise.

- **generate** — one audited kernel run (no tools granted) builds the question
  set.  Optional 学情 (``student_profile``) and web material (``source_mode``)
  are injected into the prompt so difficulty/content fit the student, and web
  adaptations are tagged with their source.
- **audit** — a second kernel run scores the paper on difficulty fit,
  coverage and quality and returns a ``pass``/``adjust`` verdict.
- **revise** — only when the audit says ``adjust``: one bounded revision round
  re-emits the questions per the audit notes.

Every model call goes through ``code_navi.providers.create_provider`` and the
kernel's ``AgentRuntime``, so each run produces an auditable Event log.  When
no online provider is configured — or web search has no key / fails — the flow
degrades to deterministic offline payloads and *does not fake a source*
(fact-boundary rule).  Generated quizzes are archived as ``notebook_items``
rows with ``item_type="quiz"``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from code_navi.providers import ProviderSettings, create_provider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

from ..models import NotebookItemModel
from .prompts import (
    AUDIT_SYSTEM_PROMPT,
    GRADE_SYSTEM_PROMPT,
    REVISE_SYSTEM_PROMPT,
    audit_user_prompt,
    build_quiz_system_prompt,
    grade_user_prompt,
    quiz_user_prompt,
    revise_user_prompt,
)
from .schemas import (
    GradeRequest,
    GradeResponse,
    QuestionType,
    QuestionGradeResult,
    QuizAuditReport,
    QuizAuditScore,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizOption,
    QuizQuestion,
    QuizQuestionSource,
    SourceMode,
)
from .websearch import WebSearchClient, _format_material

load_dotenv()

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

_DEFAULT_TIMEOUT = 60.0  # seconds — generating N questions can be slow
_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TEMPERATURE = 0.4

_ALL_TYPES: tuple[QuestionType, ...] = ("single", "fill_blank", "short_answer")


class QuizNotFoundError(Exception):
    """Raised when a quiz id is unknown, or belongs to another session."""


# ---------------------------------------------------------------------------
# Offline deterministic payloads
# ---------------------------------------------------------------------------


def _mock_questions(knowledge_point: str) -> list[QuizQuestion]:
    """Deterministic offline quiz used when no online provider is configured.

    Contains all three types and real LaTeX so the exporter can be exercised
    end-to-end with zero credentials.
    """
    return [
        QuizQuestion(
            id="q1",
            type="single",
            question=(
                "设集合 $A = \\{1, 2, 3\\}$，$B = \\{3, 4, 5\\}$，则 $A \\cap B$ 为（　）"
            ),
            options=[
                QuizOption(label="$\\{1, 3\\}$", value="A"),
                QuizOption(label="$\\{3\\}$", value="B"),
                QuizOption(label="$\\{1, 2, 3, 4, 5\\}$", value="C"),
                QuizOption(label="$\\varnothing$", value="D"),
            ],
            answer=["B"],
            analysis="两集合共有的元素只有 3。",
            points=10,
        ),
        QuizQuestion(
            id="q2",
            type="fill_blank",
            question=f"关于「{knowledge_point}」，若 $x + 2 = 5$，则 $x = $ ______。",
            answer=["3"],
            analysis="移项得 x = 5 - 2 = 3。",
            points=10,
        ),
        QuizQuestion(
            id="q3",
            type="short_answer",
            question=(
                f"证明：关于「{knowledge_point}」的集合 $A$ 与 $B$ 满足 "
                f"$A \\subseteq B$ 当且仅当 $A \\cap B = A$。"
            ),
            answer=None,
            analysis=(
                "必要性：若 A⊆B，则 A∩B 中任一元素同时属于 A 与 B，故 A∩B⊆A；"
                "又 A⊆B 且 A⊆A，所以 A⊆A∩B，故 A∩B=A。"
                "充分性：若 A∩B=A，则任一 a∈A 也属于 A∩B⊆B，故 A⊆B。"
            ),
            points=20,
            comment_prompt="(1) 证明必要性与充分性两个方向 - 60% (2) 集合运算正确性 - 40%",
        ),
    ]


def _mock_audit() -> dict:
    """Deterministic offline audit — marks the paper as passed."""
    return {
        "verdict": "pass",
        "scores": [
            {"dimension": "difficulty_fit", "score": 8, "note": "离线 Mock：未执行真实审核"},
            {"dimension": "coverage", "score": 8, "note": "离线 Mock：未执行真实审核"},
            {"dimension": "quality", "score": 8, "note": "离线 Mock：未执行真实审核"},
        ],
        "notes": [],
    }


def _mock_grade_results(
    questions: list[QuizQuestion],
    answers_map: dict[str, list[str]],
) -> list[QuestionGradeResult]:
    """Deterministic offline grading used when no online provider is configured.

    Fact-boundary rule: offline mode must *never fake an LLM verdict*.  Fill
    blanks degrade to an exact per-blank comparison (clearly labeled mock);
    short answers carry ``graded=False`` so the UI prompts self-grading.
    """
    results: list[QuestionGradeResult] = []
    for q in questions:
        given = [s.strip() for s in (answers_map.get(q.id) or [])]
        if q.type == "fill_blank":
            expected = [s.strip() for s in (q.answer or [])]
            matched = bool(expected) and given == expected
            results.append(
                QuestionGradeResult(
                    question_id=q.id,
                    type=q.type,
                    score=q.points if matched else 0,
                    max_score=q.points,
                    is_correct=matched,
                    comment=(
                        "离线 Mock 判分：与参考答案逐字一致。"
                        if matched
                        else "离线 Mock 判分：与参考答案不一致，请对照标准答案逐空检查。"
                    ),
                    is_mock=True,
                    graded=True,
                )
            )
        else:
            results.append(
                QuestionGradeResult(
                    question_id=q.id,
                    type=q.type,
                    score=0,
                    max_score=q.points,
                    is_correct=False,
                    comment="离线模式，请对照参考答案自评。",
                    is_mock=True,
                    graded=False,
                )
            )
    return results


# ---------------------------------------------------------------------------
# Parsing / normalization helpers
# ---------------------------------------------------------------------------


def _events_dir() -> Path:
    """Directory where per-run Event JSONL logs are written."""
    return Path(os.getenv("CODE_NAVI_EVENTS_DIR") or Path("var") / "runs")


def _strip_code_fence(raw: str) -> str:
    """Remove a surrounding ```json ... ``` fence if present."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    return cleaned


def _coerce_str_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _parse_source(raw: dict, *, default_web: bool) -> QuizQuestionSource:
    """Extract a question's provenance, defaulting per source mode."""
    src = raw.get("source")
    if isinstance(src, dict):
        stype = src.get("type")
        if stype not in ("generated", "web", "local_bank"):
            stype = "generated"
        label = str(src.get("label") or "").strip() or None
        uri = str(src["uri"]).strip() if src.get("uri") else None
        return QuizQuestionSource(
            type=stype,
            label=label or ("AI 生成" if stype == "generated" else "网络检索素材改编"),
            uri=uri,
            accessed_at=src.get("accessed_at"),
        )
    if default_web:
        return QuizQuestionSource(type="web", label="网络检索素材改编")
    return QuizQuestionSource()


def _normalize_question(raw: dict, index: int, *, default_web: bool = False) -> QuizQuestion | None:
    """Validate and normalize one model-emitted question dict."""
    qtype = raw.get("type")
    if qtype not in _ALL_TYPES:
        logger.warning("Skipping question with unknown type %r.", qtype)
        return None
    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        logger.warning("Skipping question without a stem (index=%d).", index)
        return None

    options: list[QuizOption] | None = None
    if qtype == "single":
        raw_options = raw.get("options")
        if not isinstance(raw_options, list) or not raw_options:
            logger.warning("Skipping single-choice without options (index=%d).", index)
            return None
        options = []
        for i, opt in enumerate(raw_options):
            if isinstance(opt, str):
                options.append(QuizOption(label=opt, value=chr(ord("A") + i)))
            elif isinstance(opt, dict):
                value = str(opt.get("value") or chr(ord("A") + i))
                label = str(opt.get("label") or opt.get("text") or value)
                options.append(QuizOption(label=label, value=value))

    analysis = raw.get("analysis")
    comment_prompt = raw.get("commentPrompt") or raw.get("comment_prompt")
    return QuizQuestion(
        id=str(raw.get("id") or f"q{index}"),
        type=qtype,
        question=question.strip(),
        options=options,
        answer=_coerce_str_list(raw.get("answer") or raw.get("correctAnswer")),
        analysis=str(analysis) if analysis else None,
        points=int(raw.get("points") or 10),
        comment_prompt=str(comment_prompt) if comment_prompt else None,
        source=_parse_source(raw, default_web=default_web),
    )


def _parse_audit(raw: str) -> QuizAuditReport | None:
    """Parse the audit JSON, returning None when it can't be trusted."""
    cleaned = _strip_code_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("verdict") not in ("pass", "adjust"):
        return None
    scores: list[QuizAuditScore] = []
    for item in (data.get("scores") or [])[:3]:
        if not isinstance(item, dict):
            continue
        dimension = item.get("dimension")
        if dimension not in ("difficulty_fit", "coverage", "quality"):
            continue
        try:
            scores.append(
                QuizAuditScore(
                    dimension=dimension,
                    score=max(0, min(10, int(item.get("score") or 0))),
                    note=str(item.get("note") or ""),
                )
            )
        except (TypeError, ValueError):
            continue
    notes = [str(n) for n in (data.get("notes") or []) if isinstance(n, str)]
    return QuizAuditReport(verdict=data["verdict"], scores=scores, notes=notes)


def _parse_grade_results(
    raw: str,
    questions: list[QuizQuestion],
) -> list[QuestionGradeResult] | None:
    """Parse the grader JSON array; return None when it can't be trusted.

    Also accepts the offline mock payload verbatim (it already carries
    ``graded``/``is_mock`` markers), so parsing the mock fallback round-trips
    to identical results instead of re-judging them as real LLM verdicts.
    """
    cleaned = _strip_code_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    by_id = {q.id: q for q in questions}
    results: list[QuestionGradeResult] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        qid = str(entry.get("question_id") or "")
        q = by_id.get(qid)
        if q is None:
            continue
        try:
            score = int(entry.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(q.points, score))
        comment = str(entry.get("comment") or "").strip() or None
        graded = bool(entry.get("graded", True))
        is_mock = bool(entry.get("is_mock", False))
        results.append(
            QuestionGradeResult(
                question_id=qid,
                type=q.type,
                score=score,
                max_score=q.points,
                is_correct=score >= q.points,
                comment=comment,
                is_mock=is_mock,
                graded=graded,
            )
        )
    return results or None


def _parse_revised(
    raw: str,
    allowed_types: list[QuestionType],
    requested_count: int,
    *,
    default_web: bool,
) -> tuple[list[QuizQuestion] | None, str | None]:
    """Parse the revision JSON into (questions, summary)."""
    cleaned = _strip_code_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        return None, None
    summary = str(data["summary"]) if data.get("summary") else None
    questions: list[QuizQuestion] = []
    for index, entry in enumerate(data["questions"]):
        if not isinstance(entry, dict):
            continue
        q = _normalize_question(entry, index, default_web=default_web)
        if q is None or q.type not in allowed_types:
            continue
        questions.append(q)
        if len(questions) >= requested_count:
            break
    return (questions or None), summary


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass
class QuizGenerator:
    """Generate → audit → (revise) one quiz set and archive it."""

    web_search: WebSearchClient = field(default_factory=WebSearchClient)

    def _provider_settings(self, offline_json: str) -> ProviderSettings:
        """Pick the provider without constructing a vendor client here."""
        name = (os.getenv("CODE_NAVI_PROVIDER") or "").strip().lower()
        if not name:
            name = "deepseek" if DEEPSEEK_API_KEY else "mock"
        if name == "mock":
            return ProviderSettings("mock", None, offline_json)
        return ProviderSettings(
            name,
            os.getenv("CODE_NAVI_MODEL") or (DEEPSEEK_MODEL if name == "deepseek" else None),
            None,
            max_tokens=_DEFAULT_MAX_TOKENS,
            temperature=_DEFAULT_TEMPERATURE,
            timeout=_DEFAULT_TIMEOUT,
            thinking="disabled" if name == "deepseek" else None,
        )

    def _run(
        self,
        system_prompt: str,
        agent_name: str,
        user_input: str,
        session_id: str,
        offline_json: str,
    ):
        """Run one audited kernel call and return (RuntimeResult, provider_name)."""
        agent = AgentSpec(
            name=agent_name,
            description=f"Generates a JSON payload for the quiz pipeline ({agent_name}).",
            system_prompt=system_prompt,
            tool_names=(),
            output_format="json",
        )
        settings = self._provider_settings(offline_json)
        provider = create_provider(settings)
        runtime = AgentRuntime(provider, session_dir=_events_dir())
        result = runtime.run(
            agent,
            RuntimeRequest(
                user_input,
                session_id=f"learning-{agent_name}-{session_id}",
                metadata={"interface": "api", "agent": agent_name, "session_id": session_id},
            ),
        )
        return result, settings.name

    # -- pipeline -----------------------------------------------------------

    def generate(self, request: QuizGenerateRequest, db: Session) -> QuizGenerateResponse:
        """Run generate → audit → (revise) and persist the quiz."""
        session_id = request.session_id or f"sess-{uuid4().hex[:16]}"
        types = request.question_types or list(_ALL_TYPES)

        # Optional web material (only when the client opts in and a key exists).
        source_mode: SourceMode = request.source_mode
        web_material: str | None = None
        if source_mode == "web":
            results = self.web_search.search(request.knowledge_point)
            if results:
                web_material = _format_material(results)
            else:
                # No key / network failure — degrade to honest pure generation.
                source_mode = "generated"

        offline = json.dumps([q.model_dump() for q in _mock_questions(request.knowledge_point)])
        system = build_quiz_system_prompt(
            types,
            student_profile=request.student_profile,
            web_material=web_material,
        )
        result, provider_name = self._run(
            system,
            "quiz_generator",
            quiz_user_prompt(
                request.knowledge_point,
                request.question_count,
                types,
                request.difficulty,
                request.with_latex,
            ),
            session_id,
            offline,
        )
        raw = result.output_text or ""
        questions = self._parse_questions(
            raw, request.question_count, types, default_web=(source_mode == "web")
        )
        if not questions:
            logger.warning("Quiz payload unparseable; falling back to mock questions.")
            questions = _mock_questions(request.knowledge_point)[: request.question_count]
            generation_mode = "rules_fallback"
        else:
            generation_mode = "rules" if provider_name == "mock" else "model"

        # Post-generation audit, then one bounded revision round if needed.
        audit = self._audit(request, session_id, questions)
        if audit is not None and audit.verdict == "adjust":
            revised, summary = self._revise(
                request, session_id, questions, types, audit.notes
            )
            if revised:
                questions = revised
                audit.revised = True
                audit.revision_summary = summary

        quiz_id = f"quiz-{uuid4().hex[:16]}"
        self._archive(
            db,
            request.knowledge_point,
            session_id,
            quiz_id,
            questions,
            generation_mode,
            provider_name,
            source_mode,
            audit,
            run_id=result.run_id,
            event_log_path=str(result.event_log_path) if result.event_log_path else None,
        )
        return QuizGenerateResponse(
            knowledge_point=request.knowledge_point,
            session_id=session_id,
            quiz_id=quiz_id,
            questions=questions,
            generation_mode=generation_mode,
            provider_name=provider_name,
            source_mode=source_mode,
            total_points=sum(q.points for q in questions),
            audit=audit,
        )

    def grade_quiz(self, request: GradeRequest) -> GradeResponse:
        """Grade fill_blank / short_answer answers through the LLM (or mock).

        Stateless: the request carries the questions and the student's answers,
        so nothing is read from or written to the database.  One audited kernel
        run scores each answered item and returns per-question score + Chinese
        comment.  Offline mode degrades honestly — exact-match for fill blanks
        (``is_mock=True``) and ``graded=False`` for short answers — never a
        faked model verdict.
        """
        questions = request.questions
        targets = [q for q in questions if q.type in ("fill_blank", "short_answer")]
        target_ids = {q.id for q in targets}
        answers_map: dict[str, list[str]] = {}
        for item in request.student_answers:
            if item.question_id in target_ids:
                answers_map[item.question_id] = item.answer

        to_grade = [q for q in targets if q.id in answers_map]
        grade_ids = {q.id for q in to_grade}
        offline = json.dumps(
            [r.model_dump() for r in _mock_grade_results(to_grade, answers_map)],
            ensure_ascii=False,
        )

        if not to_grade:
            return GradeResponse(
                session_id=request.session_id,
                results=[],
                generation_mode="rules",
                provider_name="mock",
                total_score=0,
                total_max_score=0,
            )

        questions_json = json.dumps(
            [q.model_dump(mode="json") for q in to_grade], ensure_ascii=False
        )
        answers_json = json.dumps(
            [
                {"question_id": item.question_id, "type": item.type, "answer": item.answer}
                for item in request.student_answers
                if item.question_id in grade_ids
            ],
            ensure_ascii=False,
        )
        result, provider_name = self._run(
            GRADE_SYSTEM_PROMPT,
            "quiz_grader",
            grade_user_prompt(questions_json, answers_json),
            request.session_id,
            offline,
        )
        results = _parse_grade_results(result.output_text or "", to_grade)
        if results is None:
            logger.warning("Grade payload unparseable; falling back to mock grading.")
            results = _mock_grade_results(to_grade, answers_map)
            generation_mode = "rules_fallback"
        else:
            generation_mode = "rules" if provider_name == "mock" else "model"

        return GradeResponse(
            session_id=request.session_id,
            results=results,
            generation_mode=generation_mode,
            provider_name=provider_name,
            total_score=sum(r.score for r in results if r.graded),
            total_max_score=sum(r.max_score for r in results if r.graded),
        )

    def _parse_questions(
        self,
        raw: str,
        requested_count: int,
        allowed_types: list[QuestionType],
        *,
        default_web: bool,
    ) -> list[QuizQuestion]:
        """Parse/normalize the LLM JSON array, tolerating model quirks."""
        cleaned = _strip_code_fence(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []

        questions: list[QuizQuestion] = []
        for index, entry in enumerate(data):
            if not isinstance(entry, dict):
                continue
            q = _normalize_question(entry, index, default_web=default_web)
            if q is None or q.type not in allowed_types:
                continue
            questions.append(q)
            if len(questions) >= requested_count:
                break
        return questions

    def _audit(
        self,
        request: QuizGenerateRequest,
        session_id: str,
        questions: list[QuizQuestion],
    ) -> QuizAuditReport | None:
        """Second kernel run scoring the paper; None when unparseable."""
        questions_json = json.dumps(
            [q.model_dump(mode="json") for q in questions], ensure_ascii=False
        )
        result, _ = self._run(
            AUDIT_SYSTEM_PROMPT,
            "quiz_audit",
            audit_user_prompt(
                questions_json,
                request.knowledge_point,
                request.difficulty,
                request.student_profile,
            ),
            session_id,
            json.dumps(_mock_audit(), ensure_ascii=False),
        )
        audit = _parse_audit(result.output_text or "")
        if audit is None:
            logger.warning("Audit payload unparseable; no audit will be reported.")
        return audit

    def _revise(
        self,
        request: QuizGenerateRequest,
        session_id: str,
        questions: list[QuizQuestion],
        allowed_types: list[QuestionType],
        audit_notes: list[str],
    ) -> tuple[list[QuizQuestion] | None, str | None]:
        """One bounded revision round per the audit notes."""
        questions_json = json.dumps(
            [q.model_dump(mode="json") for q in questions], ensure_ascii=False
        )
        offline = json.dumps(
            {
                "summary": "离线 Mock：未触发真实修订",
                "questions": [q.model_dump() for q in _mock_questions(request.knowledge_point)],
            },
            ensure_ascii=False,
        )
        result, _ = self._run(
            REVISE_SYSTEM_PROMPT,
            "quiz_revise",
            revise_user_prompt(audit_notes, questions_json),
            session_id,
            offline,
        )
        revised, summary = _parse_revised(
            result.output_text or "",
            allowed_types,
            request.question_count,
            default_web=(request.source_mode == "web"),
        )
        if revised is None:
            logger.warning("Revision payload unparseable; keeping the original questions.")
        return revised, summary

    def _archive(
        self,
        db: Session,
        knowledge_point: str,
        session_id: str,
        quiz_id: str,
        questions: list[QuizQuestion],
        generation_mode: str,
        provider_name: str,
        source_mode: SourceMode,
        audit: QuizAuditReport | None,
        *,
        run_id: str | None = None,
        event_log_path: str | None = None,
    ) -> None:
        """Persist the generated quiz as a ``quiz`` notebook item."""
        entry = NotebookItemModel(
            user_id="poc-user",  # TODO: replace with real auth user id
            session_id=session_id,
            knowledge_id=knowledge_point,
            item_type="quiz",
            content=knowledge_point,
            extra_data={
                "quiz_id": quiz_id,
                "questions": [q.model_dump() for q in questions],
                "generation_mode": generation_mode,
                "provider_name": provider_name,
                "source_mode": source_mode,
                "audit": audit.model_dump() if audit else None,
                "run_id": run_id,
                "event_log_path": event_log_path,
            },
        )
        db.add(entry)
        db.commit()

    @staticmethod
    def load_quiz(db: Session, session_id: str, quiz_id: str) -> tuple[str, list[QuizQuestion]]:
        """Read a quiz back, strictly scoped to the requesting session."""
        items = (
            db.query(NotebookItemModel)
            .filter(
                NotebookItemModel.user_id == "poc-user",
                NotebookItemModel.session_id == session_id,
                NotebookItemModel.item_type == "quiz",
            )
            .all()
        )
        item = next(
            (i for i in items if (i.extra_data or {}).get("quiz_id") == quiz_id),
            None,
        )
        if item is None:
            raise QuizNotFoundError("Quiz not found for this session")
        questions = [
            QuizQuestion.model_validate(q)
            for q in (item.extra_data or {}).get("questions", [])
        ]
        return item.knowledge_id, questions


__all__ = [
    "QuizGenerator",
    "QuizNotFoundError",
    "WebSearchClient",
    "_mock_questions",
    "_mock_grade_results",
    "_parse_grade_results",
]
