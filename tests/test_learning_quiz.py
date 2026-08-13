"""Tests for the learning quiz module: generation, persistence, docx export.

Covered surfaces:
- generator runs through the kernel with the mock provider and archives a quiz
- LLM JSON normalization tolerates model quirks (string/object options, single
  string answers, unknown types being skipped, missing fields)
- the docx exporter produces a valid Word file with OMML equations, the skill's
  margins/indents/tab stops, section headers and an optional answer section
- the export endpoint is strictly session-scoped (cross-session → 404)
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Force in-memory SQLite *before* any code_navi.learning imports execute.
os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.learning.models import NotebookItemModel  # noqa: E402
from code_navi.learning.quiz.docx import export_quiz_docx  # noqa: E402
from code_navi.learning.quiz.schemas import (  # noqa: E402
    GradeRequest,
    QuizAuditReport,
    QuizGenerateRequest,
    QuizOption,
    QuizQuestion,
    QuizQuestionSource,
    StudentAnswerItem,
)
from code_navi.learning.quiz.services import (  # noqa: E402
    QuizGenerator,
    QuizNotFoundError,
    _mock_grade_results,
    _mock_questions,
    _normalize_question,
    _parse_audit,
    _parse_grade_results,
    _parse_revised,
)
from code_navi.learning.quiz.websearch import WebSearchClient  # noqa: E402
from code_navi.server import app  # noqa: E402
from kernel.adapters.jsonl_session import load_session  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_event_logs(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep kernel Event JSONL out of the working tree during tests."""
    monkeypatch.setenv("CODE_NAVI_EVENTS_DIR", str(tmp_path_factory.mktemp("events")))


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep quiz tests offline even when a local .env has a key."""
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    """Recreate all tables before each test so tests are fully isolated."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a per-test database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """FastAPI TestClient wired to the in-memory database."""
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# Generation / persistence
# ---------------------------------------------------------------------------


class TestQuizGenerator:
    def test_generate_with_mock_provider(self, db: Session) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(knowledge_point="集合"),
            db,
        )

        assert response.session_id.startswith("sess-")
        assert response.quiz_id.startswith("quiz-")
        assert response.generation_mode == "rules"
        assert response.provider_name == "mock"
        assert response.total_points == sum(q.points for q in response.questions)
        # mock payload covers all three types
        assert {q.type for q in response.questions} == {
            "single",
            "fill_blank",
            "short_answer",
        }

    def test_generate_persists_quiz_notebook_item(self, db: Session) -> None:
        generator = QuizGenerator()
        response = generator.generate(
            QuizGenerateRequest(knowledge_point="函数单调性", session_id="sess-q"),
            db,
        )

        item = (
            db.query(NotebookItemModel)
            .filter(
                NotebookItemModel.session_id == "sess-q",
                NotebookItemModel.item_type == "quiz",
            )
            .first()
        )
        assert item is not None
        assert item.extra_data["quiz_id"] == response.quiz_id
        assert len(item.extra_data["questions"]) == len(response.questions)

    def test_generate_writes_auditable_event_log(self, db: Session) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(knowledge_point="排列组合"),
            db,
        )
        items = db.query(NotebookItemModel).filter_by(item_type="quiz").all()
        item = next(
            i for i in items if (i.extra_data or {}).get("quiz_id") == response.quiz_id
        )
        assert item is not None
        log_path = Path(item.extra_data["event_log_path"])
        assert log_path.is_file()
        events = load_session(log_path)
        event_types = {e.type for e in events}
        assert {"run_started", "provider_called", "run_finished"} <= event_types

    def test_generate_mints_session_when_omitted(self, db: Session) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(knowledge_point="导数"),
            db,
        )
        assert response.session_id.startswith("sess-")

    @pytest.mark.parametrize("question_count", [1, 3, 5])
    def test_generate_honors_requested_count(
        self, db: Session, question_count: int
    ) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(
                knowledge_point="集合",
                session_id=f"sess-count-{question_count}",
                question_count=question_count,
            ),
            db,
        )

        assert len(response.questions) == question_count
        assert len({question.id for question in response.questions}) == question_count

    def test_generate_honors_selected_question_type(self, db: Session) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(
                knowledge_point="集合",
                session_id="sess-single-only",
                question_count=5,
                question_types=["single"],
            ),
            db,
        )

        assert len(response.questions) == 5
        assert {question.type for question in response.questions} == {"single"}
        assert len({question.question for question in response.questions}) == 5

    def test_generate_rejects_unstable_large_paper(self) -> None:
        with pytest.raises(ValueError):
            QuizGenerateRequest(knowledge_point="集合", question_count=6)

    def test_parse_questions_rejects_partial_model_paper(self) -> None:
        questions = QuizGenerator()._parse_questions(
            json.dumps(
                [
                    {
                        "id": "q1",
                        "type": "fill_blank",
                        "question": "x = ______",
                        "answer": ["1"],
                        "analysis": "解析",
                        "points": 10,
                    }
                ]
            ),
            requested_count=2,
            allowed_types=["fill_blank"],
            default_web=False,
        )

        assert questions == []

    def test_parse_questions_rejects_duplicate_ids(self) -> None:
        raw_question = {
            "id": "duplicate",
            "type": "fill_blank",
            "question": "x = ______",
            "answer": ["1"],
            "analysis": "解析",
            "points": 10,
        }
        questions = QuizGenerator()._parse_questions(
            json.dumps([raw_question, raw_question]),
            requested_count=2,
            allowed_types=["fill_blank"],
            default_web=False,
        )

        assert questions == []

    def test_load_quiz_is_session_scoped(self, db: Session) -> None:
        gen = QuizGenerator()
        quiz_a = gen.generate(
            QuizGenerateRequest(knowledge_point="集合", session_id="sess-a"),
            db,
        )
        quiz_b = gen.generate(
            QuizGenerateRequest(knowledge_point="集合", session_id="sess-b"),
            db,
        )

        # Reading session-a's quiz from session-b must fail.
        with pytest.raises(QuizNotFoundError):
            gen.load_quiz(db, "sess-b", quiz_a.quiz_id)
        # ...and succeed within its own session.
        knowledge_point, questions = gen.load_quiz(db, "sess-b", quiz_b.quiz_id)
        assert knowledge_point == "集合"
        assert questions


# ---------------------------------------------------------------------------
# JSON normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_single_choice_object_options(self) -> None:
        q = _normalize_question(
            {
                "id": "q1",
                "type": "single",
                "question": "1+1=?",
                "options": [
                    {"label": "A内容", "value": "A"},
                    {"label": "B内容", "value": "B"},
                ],
                "answer": "A",
                "analysis": "解析",
            },
            0,
        )
        assert q is not None
        assert q.type == "single"
        assert q.answer == ["A"]
        assert [o.value for o in q.options] == ["A", "B"]

    def test_single_choice_string_options_get_letter_values(self) -> None:
        q = _normalize_question(
            {"id": "q2", "type": "single", "question": "x?", "options": ["甲", "乙"]},
            0,
        )
        assert q is not None
        assert q.options == [QuizOption(label="甲", value="A"), QuizOption(label="乙", value="B")]

    def test_single_choice_without_options_is_rejected(self) -> None:
        assert _normalize_question({"type": "single", "question": "无选项"}, 0) is None

    def test_unknown_type_is_rejected(self) -> None:
        assert _normalize_question({"type": "essay", "question": "?"}, 0) is None

    def test_missing_stem_is_rejected(self) -> None:
        assert _normalize_question({"type": "single", "options": []}, 0) is None

    def test_fill_blank_multiple_answers(self) -> None:
        q = _normalize_question(
            {
                "type": "fill_blank",
                "question": "a=___, b=___",
                "answer": ["1", "2"],
                "analysis": "…",
            },
            0,
        )
        assert q is not None
        assert q.answer == ["1", "2"]

    def test_short_answer_comment_prompt_snake_and_camel(self) -> None:
        camel = _normalize_question(
            {"type": "short_answer", "question": "证明", "commentPrompt": "要点"},
            0,
        )
        snake = _normalize_question(
            {"type": "short_answer", "question": "证明", "comment_prompt": "要点"},
            0,
        )
        assert camel is not None and camel.comment_prompt == "要点"
        assert snake is not None and snake.comment_prompt == "要点"


# ---------------------------------------------------------------------------
# docx exporter
# ---------------------------------------------------------------------------


def _read_document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


class TestDocxExporter:
    def _quiz(self) -> list[QuizQuestion]:
        return _mock_questions("集合")

    def test_export_produces_valid_docx_zip(self) -> None:
        docx_bytes = export_quiz_docx(knowledge_point="集合", questions=self._quiz())
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            assert "[Content_Types].xml" in zf.namelist()
            assert "word/document.xml" in zf.namelist()

    def test_export_uses_narrow_margins(self) -> None:
        xml = _read_document_xml(
            export_quiz_docx(knowledge_point="集合", questions=self._quiz())
        )
        # 720 twips = 1.27 cm on every side, matching the typesetting skill.
        assert 'w:top="720"' in xml
        assert 'w:bottom="720"' in xml
        assert 'w:left="720"' in xml
        assert 'w:right="720"' in xml

    def test_export_embeds_native_omml_equations(self) -> None:
        xml = _read_document_xml(
            export_quiz_docx(knowledge_point="集合", questions=self._quiz())
        )
        assert "<m:oMath" in xml  # LaTeX rendered as real Word equations
        assert "$" not in xml  # no raw LaTeX delimiters left in the document

    def test_export_section_headers_and_continuous_numbering(self) -> None:
        xml = _read_document_xml(
            export_quiz_docx(knowledge_point="集合", questions=self._quiz())
        )
        for header in ("一、单项选择题", "二、填空题", "三、解答题"):
            assert header in xml
        # Continuous numbering across sections: 1, 2, 3 appear as stems.
        for number in ("1. ", "2. ", "3. "):
            assert number in xml

    def test_export_options_use_tab_stops(self) -> None:
        xml = _read_document_xml(
            export_quiz_docx(knowledge_point="集合", questions=self._quiz())
        )
        # Options must be tab-separated (the skill's tab-stop alignment), not
        # pushed together with plain spaces. Both layouts define <w:tabs>.
        assert "<w:tabs>" in xml
        assert xml.count("<w:tab ") >= 2

    def test_export_with_answer_appends_answer_section(self) -> None:
        plain = _read_document_xml(
            export_quiz_docx(knowledge_point="集合", questions=self._quiz())
        )
        answered = _read_document_xml(
            export_quiz_docx(
                knowledge_point="集合", questions=self._quiz(), with_answer=True
            )
        )
        assert "参考答案" not in plain
        assert "参考答案" in answered

    def test_export_answer_does_not_duplicate_short_answer_analysis(self) -> None:
        xml = _read_document_xml(
            export_quiz_docx(
                knowledge_point="集合", questions=self._quiz(), with_answer=True
            )
        )
        # The short-answer's reference answer embeds its analysis; a separate
        # 解析 line would print it twice. Only single + fill_blank get one.
        assert xml.count("解析：") == 2
        assert xml.count("充分性") == 1  # appears only once, inside 参考答案

    def test_export_falls_back_to_text_for_bad_latex(self) -> None:
        questions = [
            QuizQuestion(
                id="bad",
                type="short_answer",
                question="含异常公式 $\\frac{$ 未闭合",
                answer=None,
                analysis="…",
            )
        ]
        # Must not raise — the bad formula degrades to literal text.
        xml = _read_document_xml(
            export_quiz_docx(knowledge_point="容错", questions=questions)
        )
        assert "未闭合" in xml

    def test_export_blank_lines_have_no_literal_nbsp(self) -> None:
        # Short-answer writing space must be empty lines, never the visible
        # text ``&nbsp;`` (python-docx does not decode HTML entities).
        questions = [q for q in self._quiz() if q.type == "short_answer"]
        xml = _read_document_xml(export_quiz_docx(knowledge_point="集合", questions=questions))
        assert "&nbsp;" not in xml  # no literal HTML entity leaks into the run
        assert " " in xml or "&#160;" in xml  # a real no-break space keeps the line


# ---------------------------------------------------------------------------
# Export endpoint (session scoping)
# ---------------------------------------------------------------------------


class TestExportEndpoint:
    def _generate(self, client: TestClient, session_id: str) -> dict:
        resp = client.post(
            "/api/v1/learning/quiz/generate",
            json={"knowledge_point": "集合", "session_id": session_id},
        )
        assert resp.status_code == 200
        return resp.json()

    def test_export_returns_docx(self, client: TestClient) -> None:
        quiz = self._generate(client, "sess-export")
        resp = client.get(
            "/api/v1/learning/quiz/export-docx",
            params={"quiz_id": quiz["quiz_id"], "session_id": "sess-export"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert "attachment" in resp.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            assert "word/document.xml" in zf.namelist()

    def test_export_with_answer_flag(self, client: TestClient) -> None:
        quiz = self._generate(client, "sess-export2")
        resp = client.get(
            "/api/v1/learning/quiz/export-docx",
            params={
                "quiz_id": quiz["quiz_id"],
                "session_id": "sess-export2",
                "with_answer": "true",
            },
        )
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "参考答案" in xml

    def test_export_cross_session_returns_404(self, client: TestClient) -> None:
        quiz = self._generate(client, "sess-alice")
        resp = client.get(
            "/api/v1/learning/quiz/export-docx",
            params={"quiz_id": quiz["quiz_id"], "session_id": "sess-bob"},
        )
        assert resp.status_code == 404

    def test_export_unknown_quiz_returns_404(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/learning/quiz/export-docx",
            params={"quiz_id": "quiz-nope", "session_id": "sess-x"},
        )
        assert resp.status_code == 404

    def test_export_requires_session_id(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/learning/quiz/export-docx",
            params={"quiz_id": "quiz-x"},
        )
        assert resp.status_code == 422

    def test_generate_validates_question_count(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/quiz/generate",
            json={"knowledge_point": "集合", "question_count": 0},
        )
        assert resp.status_code == 422

    def test_services_module_does_not_import_vendor_sdk(self) -> None:
        from code_navi.learning.quiz import services

        source = Path(services.__file__).read_text(encoding="utf-8")
        assert "from openai import" not in source
        assert "OpenAI(" not in source


# ---------------------------------------------------------------------------
# Provenance / web fallback / 学情 / review
# ---------------------------------------------------------------------------


class TestSourceAndReview:
    def test_questions_carry_generated_source(self, db: Session) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(knowledge_point="集合"),
            db,
        )
        assert response.source_mode == "generated"
        assert all(q.source.type == "generated" for q in response.questions)
        assert all(q.source.label == "AI 生成" for q in response.questions)

    def test_web_mode_falls_back_without_api_key(self, db: Session) -> None:
        # No TAVILY_API_KEY is configured in tests → honest fallback to generated.
        response = QuizGenerator().generate(
            QuizGenerateRequest(knowledge_point="集合", source_mode="web"),
            db,
        )
        assert response.source_mode == "generated"
        assert all(q.source.type == "generated" for q in response.questions)

    def test_generate_accepts_student_profile(self, db: Session) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(
                knowledge_point="集合",
                student_profile="该生对集合运算薄弱，已掌握列举法；请适当降低难度，多出基础题。",
                difficulty="easy",
            ),
            db,
        )
        assert response.questions
        assert response.total_points > 0

    def test_audit_reported_in_mock_mode(self, db: Session) -> None:
        response = QuizGenerator().generate(
            QuizGenerateRequest(knowledge_point="集合"),
            db,
        )
        assert response.audit is not None
        assert response.audit.verdict == "pass"
        assert {s.dimension for s in response.audit.scores} == {
            "difficulty_fit",
            "coverage",
            "quality",
        }

    def test_adjust_audit_triggers_one_revision_round(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gen = QuizGenerator()

        def fake_audit(request, session_id, questions) -> QuizAuditReport:
            return QuizAuditReport(verdict="adjust", scores=[], notes=["难度偏高，请降低"])

        def fake_revise(request, session_id, questions, types, notes):
            revised = [
                q.model_copy(
                    update={"source": QuizQuestionSource(type="web", label="已修订")}
                )
                for q in questions
            ]
            return revised, "已按审核意见降低难度"

        monkeypatch.setattr(gen, "_audit", fake_audit)
        monkeypatch.setattr(gen, "_revise", fake_revise)

        response = gen.generate(QuizGenerateRequest(knowledge_point="集合"), db)
        assert response.audit is not None
        assert response.audit.revised is True
        assert response.audit.revision_summary == "已按审核意见降低难度"
        assert all(q.source.label == "已修订" for q in response.questions)

    def test_parse_audit_accepts_valid_json(self) -> None:
        audit = _parse_audit(
            '{"verdict": "adjust", "scores": [{"dimension": "quality", "score": 6, '
            '"note": "选项有歧义"}], "notes": ["修正 B 选项"]}'
        )
        assert audit is not None
        assert audit.verdict == "adjust"
        assert audit.scores[0].dimension == "quality"
        assert audit.notes == ["修正 B 选项"]

    def test_parse_audit_rejects_invalid_json(self) -> None:
        assert _parse_audit("not json") is None
        assert _parse_audit('{"verdict": "unknown"}') is None

    def test_parse_revised_returns_questions_and_summary(self) -> None:
        questions, summary = _parse_revised(
            '{"summary": "修订完成", "questions": [{"type": "single", "question": "x?", '
            '"options": ["甲", "乙"], "answer": ["A"], "analysis": "…", "points": 10}]}',
            ["single"],
            1,
            default_web=False,
        )
        assert summary == "修订完成"
        assert questions is not None and len(questions) == 1

    def test_parse_revised_rejects_malformed_payload(self) -> None:
        questions, summary = _parse_revised('{"summary": "x"}', ["single"], 5, default_web=False)
        assert questions is None
        assert summary is None

    def test_normalize_question_parses_source(self) -> None:
        q = _normalize_question(
            {
                "type": "fill_blank",
                "question": "x = ___",
                "answer": ["1"],
                "source": {"type": "web", "label": "改编自某教材", "uri": "https://example.com"},
            },
            0,
        )
        assert q is not None
        assert q.source.type == "web"
        assert q.source.label == "改编自某教材"
        assert q.source.uri == "https://example.com"

    def test_web_search_client_is_inert_without_key(self) -> None:
        client = WebSearchClient(api_key="")
        assert client.available is False
        assert client.search("集合") == []


# ---------------------------------------------------------------------------
# LLM grading (fill_blank / short_answer) — mock downgrade is honest
# ---------------------------------------------------------------------------


class TestQuizGrader:
    """Service-level grading: offline mode never fakes an LLM verdict."""

    def _grade(
        self,
        db: Session,
        session_id: str,
        student_answers: list[StudentAnswerItem],
    ) -> object:
        """Generate a quiz (archives it), then grade it server-side by quiz id."""
        gen = QuizGenerator()
        quiz = gen.generate(
            QuizGenerateRequest(knowledge_point="集合", session_id=session_id),
            db,
        )
        return gen.grade_quiz(
            GradeRequest(
                session_id=session_id,
                quiz_id=quiz.quiz_id,
                student_answers=student_answers,
            ),
            db,
        )

    def test_grade_fill_blank_correct_in_mock_mode(self, db: Session) -> None:
        response = self._grade(
            db,
            "sess-g",
            [StudentAnswerItem(question_id="q2", answer=["3"])],
        )
        assert response.generation_mode == "rules"
        assert response.provider_name == "mock"
        assert len(response.results) == 1
        result = response.results[0]
        assert result.question_id == "q2"
        assert result.score == result.max_score == 10
        assert result.is_correct is True
        assert result.is_mock is True  # honest offline label, not a model verdict
        assert result.graded is True
        assert "离线 Mock 判分" in (result.comment or "")

    def test_grade_fill_blank_wrong_in_mock_mode(self, db: Session) -> None:
        response = self._grade(
            db,
            "sess-g",
            [StudentAnswerItem(question_id="q2", answer=["999"])],
        )
        result = response.results[0]
        assert result.score == 0
        assert result.is_correct is False
        assert result.is_mock is True

    def test_grade_short_answer_is_ungraded_in_mock_mode(self, db: Session) -> None:
        response = self._grade(
            db,
            "sess-g",
            [StudentAnswerItem(question_id="q3", answer=["因为 A⊆B，所以 A∩B=A…"])],
        )
        result = response.results[0]
        assert result.graded is False  # must prompt self-grading, never fake a score
        assert result.is_mock is True
        assert result.score == 0
        assert "请对照参考答案自评" in (result.comment or "")

    def test_grade_aggregates_over_graded_results_only(self, db: Session) -> None:
        response = self._grade(
            db,
            "sess-g",
            [
                StudentAnswerItem(question_id="q2", answer=["3"]),
                StudentAnswerItem(question_id="q3", answer=["证明：…"]),
            ],
        )
        assert len(response.results) == 2
        # q3 is ungraded → excluded from the auto totals so a self-graded short
        # answer never drags the objective score down.
        assert response.total_score == 10
        assert response.total_max_score == 10

    def test_grade_skips_single_and_unanswered_questions(self, db: Session) -> None:
        response = self._grade(
            db,
            "sess-g",
            [StudentAnswerItem(question_id="q1", answer=["B"])],
        )
        assert response.results == []
        assert response.total_score == 0
        assert response.total_max_score == 0

    def test_grade_unknown_quiz_raises(self, db: Session) -> None:
        gen = QuizGenerator()
        with pytest.raises(QuizNotFoundError):
            gen.grade_quiz(
                GradeRequest(session_id="sess-g", quiz_id="quiz-nope", student_answers=[]),
                db,
            )


class TestParseGradeResults:
    @staticmethod
    def _questions() -> list[QuizQuestion]:
        return [
            question
            for question in _mock_questions("集合")
            if question.type in ("fill_blank", "short_answer")
        ]

    def test_accepts_valid_json(self) -> None:
        questions = self._questions()
        results = _parse_grade_results(
            '[{"question_id": "q2", "score": 10, "comment": "答对了"}, '
            '{"question_id": "q3", "score": 15, "comment": "思路清晰，缺一步"}]',
            questions,
        )
        assert results is not None
        by_id = {r.question_id: r for r in results}
        assert by_id["q2"].score == 10 and by_id["q2"].is_correct is True
        assert by_id["q2"].comment == "答对了"
        assert by_id["q2"].is_mock is False and by_id["q2"].graded is True
        assert by_id["q3"].score == 15 and by_id["q3"].is_correct is False  # 20 pts max

    def test_clamps_score_to_question_bounds(self) -> None:
        questions = self._questions()
        results = _parse_grade_results(
            '[{"question_id": "q2", "score": 99, "comment": "超分"}, '
            '{"question_id": "q3", "score": -5, "comment": "负分"}]',
            questions,
        )
        assert results is not None
        by_id = {r.question_id: r for r in results}
        assert by_id["q2"].score == 10  # q2 max 10
        assert by_id["q3"].score == 0  # q3 max 20, floor 0

    def test_rejects_invalid_payloads(self) -> None:
        questions = self._questions()
        assert _parse_grade_results("not json", questions) is None
        assert _parse_grade_results('{"not": "an array"}', questions) is None
        assert _parse_grade_results("[]", questions) is None

    def test_rejects_partial_results(self) -> None:
        questions = self._questions()
        assert _parse_grade_results(
            '[{"question_id": "q2", "score": 10}]',
            questions,
        ) is None

    def test_rejects_duplicate_results(self) -> None:
        questions = self._questions()
        assert _parse_grade_results(
            '[{"question_id": "q2", "score": 10}, '
            '{"question_id": "q2", "score": 10}, '
            '{"question_id": "q3", "score": 15}]',
            questions,
        ) is None

    def test_ignores_unknown_question_ids_when_expected_results_are_complete(self) -> None:
        questions = self._questions()
        results = _parse_grade_results(
            '[{"question_id": "nope", "score": 10}, '
            '{"question_id": "q2", "score": 10}, '
            '{"question_id": "q3", "score": 15}]',
            questions,
        )

        assert results is not None
        assert {result.question_id for result in results} == {"q2", "q3"}

    def test_mock_payload_round_trips_graded_and_is_mock(self) -> None:
        questions = self._questions()
        answers_map = {"q2": ["3"], "q3": ["证明"]}
        mock = _mock_grade_results(questions, answers_map)
        raw = json.dumps([r.model_dump() for r in mock], ensure_ascii=False)
        parsed = _parse_grade_results(raw, questions)
        assert parsed is not None
        by_id = {r.question_id: r for r in parsed}
        assert by_id["q3"].graded is False  # offline short answer stays ungraded
        assert by_id["q3"].is_mock is True
        assert by_id["q2"].graded is True and by_id["q2"].is_mock is True


class TestGradeEndpoint:
    def _generate(self, client: TestClient, session_id: str) -> dict:
        resp = client.post(
            "/api/v1/learning/quiz/generate",
            json={"knowledge_point": "集合", "session_id": session_id},
        )
        assert resp.status_code == 200
        return resp.json()

    def _grade_payload(self, client: TestClient, session_id: str = "sess-grade") -> dict:
        quiz = self._generate(client, session_id)
        return {
            "session_id": session_id,
            "quiz_id": quiz["quiz_id"],
            "student_answers": [
                {"question_id": "q2", "answer": ["3"]},
                {"question_id": "q3", "answer": ["因为…"]},
            ],
        }

    def test_grade_returns_results(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/quiz/grade", json=self._grade_payload(client)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-grade"
        assert data["generation_mode"] == "rules"
        assert data["provider_name"] == "mock"
        by_id = {r["question_id"]: r for r in data["results"]}
        assert by_id["q2"]["score"] == 10
        assert by_id["q2"]["is_correct"] is True
        assert by_id["q2"]["is_mock"] is True
        assert by_id["q3"]["graded"] is False
        assert data["total_score"] == 10

    def test_grade_requires_session_id(self, client: TestClient) -> None:
        payload = self._grade_payload(client)
        payload.pop("session_id")
        resp = client.post("/api/v1/learning/quiz/grade", json=payload)
        assert resp.status_code == 422

    def test_grade_requires_quiz_id(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/quiz/grade",
            json={"session_id": "sess-x", "student_answers": []},
        )
        assert resp.status_code == 422

    def test_grade_unknown_quiz_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/quiz/grade",
            json={
                "session_id": "sess-x",
                "quiz_id": "quiz-nope",
                "student_answers": [],
            },
        )
        assert resp.status_code == 404

    def test_grade_cross_session_returns_404(self, client: TestClient) -> None:
        quiz = self._generate(client, "sess-alice")
        resp = client.post(
            "/api/v1/learning/quiz/grade",
            json={
                "session_id": "sess-bob",
                "quiz_id": quiz["quiz_id"],
                "student_answers": [{"question_id": "q2", "answer": ["3"]}],
            },
        )
        assert resp.status_code == 404

    def test_grade_rejects_unknown_student_question_ids(self, client: TestClient) -> None:
        payload = self._grade_payload(client)
        payload["student_answers"] = [
            {"question_id": "ghost", "answer": ["x"]},
        ]
        resp = client.post("/api/v1/learning/quiz/grade", json=payload)
        assert resp.status_code == 200
        assert resp.json()["results"] == []  # unknown ids are filtered, not errors


class TestPackageData:
    """The OMML stylesheet must ship inside the built wheel (not just the source)."""

    def test_mml2omml_xsl_is_in_wheel(self, tmp_path: Path) -> None:
        root = Path(__file__).resolve().parents[1]
        out_dir = tmp_path / "dist"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(out_dir),
            ],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        wheels = list(out_dir.glob("*.whl"))
        assert wheels, "wheel build produced no artifact"
        with zipfile.ZipFile(wheels[0]) as zf:
            names = zf.namelist()
        assert "code_navi/learning/quiz/MML2OMML.XSL" in names
