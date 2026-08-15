"""Tests for the learning portrait (学情画像) module.

Covered surfaces:
- ``ProfileService.get_profile`` aggregates real persisted scores only and
  reports 样本不足 (``mastery=None``) below the minimum sample size — never a
  fabricated percentage; ``graded=False`` rows are excluded.
- ``ProfileService.set_mark`` upserts the binary 不懂/懂了 toggle idempotently
  on ``(session_id, source_type, source_ref)``; a mark without a ``profile_id``
  stays out of the portrait.
- ``POST /api/v1/learning/marks`` and ``GET /api/v1/profile`` endpoints,
  including unknown-key → empty 200 (never 404) and invalid UUID → 422.
- The full generate → grade → portrait flow persists attempts under the
  client-minted ``profile_id`` and surfaces them in the portrait.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Force in-memory SQLite *before* any code_navi imports execute.
os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.learning.quiz.schemas import (  # noqa: E402
    GradeRequest,
    QuizGenerateRequest,
    StudentAnswerItem,
)
from code_navi.learning.quiz.services import QuizGenerator  # noqa: E402
from code_navi.learning_profile.models import (  # noqa: E402
    ConfusionMarkModel,
    QuizAttemptModel,
)
from code_navi.learning_profile.schemas import MarkRequest  # noqa: E402
from code_navi.learning_profile.service import ProfileService  # noqa: E402
from code_navi.server import app  # noqa: E402

PROFILE_A = "22222222-2222-4222-8222-222222222222"
PROFILE_B = "33333333-3333-4333-8333-333333333333"

ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    """Recreate all tables before each test so tests are fully isolated."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as tc:
        yield tc


def _add_attempt(
    db: Session,
    *,
    knowledge_point: str,
    score: int,
    max_score: int,
    graded: bool = True,
    profile_id: str = PROFILE_A,
    session_id: str = "sess-a",
) -> None:
    db.add(
        QuizAttemptModel(
            attempt_id=str(uuid.uuid4()),
            quiz_id="quiz-x",
            session_id=session_id,
            knowledge_point=knowledge_point,
            profile_id=profile_id,
            user_id=None,
            question_id="q1",
            question_type="single",
            points=max_score,
            score=score,
            max_score=max_score,
            correct=score >= max_score,
            graded=graded,
            graded_by="rules",
            is_mock=False,
            comment=None,
        )
    )
    db.commit()


def _add_mark(
    db: Session,
    *,
    knowledge_point: str,
    source_ref: str = "explain:集合",
    source_type: str = "explain",
    status: str = "confused",
    profile_id: str = PROFILE_A,
    session_id: str = "sess-a",
) -> None:
    db.add(
        ConfusionMarkModel(
            session_id=session_id,
            profile_id=profile_id,
            user_id=None,
            knowledge_point=knowledge_point,
            source_type=source_type,
            source_ref=source_ref,
            status=status,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Service: portrait aggregation (facts only, no fabricated numbers)
# ---------------------------------------------------------------------------


class TestProfileAggregation:
    def test_mastery_computed_from_graded_scores(self, db: Session) -> None:
        _add_attempt(db, knowledge_point="集合", score=10, max_score=10)
        _add_attempt(db, knowledge_point="集合", score=10, max_score=10)
        _add_attempt(db, knowledge_point="集合", score=10, max_score=10)
        _add_attempt(db, knowledge_point="函数", score=2, max_score=10)

        profile = ProfileService().get_profile(PROFILE_A, db)

        by_point = {m.knowledge_point: m for m in profile.mastery}
        jihe = by_point["集合"]
        assert jihe.quiz_rate == 1.0
        assert jihe.sample_size == 3
        assert jihe.status == "sufficient"
        assert jihe.mastery == 1.0
        han = by_point["函数"]
        assert han.quiz_rate == 0.2
        assert han.sample_size == 1
        assert han.status == "insufficient"
        assert han.mastery is None

    def test_insufficient_sample_never_reports_fake_percentage(
        self, db: Session
    ) -> None:
        _add_attempt(db, knowledge_point="集合", score=8, max_score=10)
        _add_attempt(db, knowledge_point="集合", score=6, max_score=10)

        profile = ProfileService().get_profile(PROFILE_A, db)
        entry = profile.mastery[0]
        # Real score rate is 70%, but with only 2 samples it must NOT be shown
        # as a mastery value — that is the fact boundary.
        assert entry.quiz_rate == 0.7
        assert entry.mastery is None
        assert entry.status == "insufficient"

    def test_ungraded_attempts_are_excluded(self, db: Session) -> None:
        # An offline-mode short answer comes back graded=False; it must not
        # count toward sample size or mastery.
        _add_attempt(db, knowledge_point="集合", score=10, max_score=10, graded=True)
        _add_attempt(db, knowledge_point="集合", score=0, max_score=20, graded=False)

        profile = ProfileService().get_profile(PROFILE_A, db)
        entry = profile.mastery[0]
        assert entry.sample_size == 1
        assert entry.quiz_rate == 1.0
        assert entry.status == "insufficient"  # only 1 graded sample

    def test_attempts_without_profile_id_are_ignored(self, db: Session) -> None:
        _add_attempt(db, knowledge_point="集合", score=10, max_score=10, profile_id=None)
        profile = ProfileService().get_profile(PROFILE_A, db)
        assert profile.mastery == []

    def test_portrait_is_cross_session(self, db: Session) -> None:
        _add_attempt(db, knowledge_point="集合", score=10, max_score=10, session_id="sess-a")
        _add_attempt(db, knowledge_point="集合", score=0, max_score=10, session_id="sess-b")
        _add_attempt(db, knowledge_point="集合", score=10, max_score=10, session_id="sess-c")

        profile = ProfileService().get_profile(PROFILE_A, db)
        entry = profile.mastery[0]
        assert entry.sample_size == 3
        assert entry.quiz_rate == pytest.approx(2 / 3)

    def test_strengths_and_weaknesses_thresholds(self, db: Session) -> None:
        for point, score, max_score in [
            ("强项A", 10, 10),
            ("强项B", 8, 10),
            ("强项C", 9, 10),
            ("弱项", 1, 10),
            ("中等", 7, 10),
        ]:
            for _ in range(3):
                _add_attempt(db, knowledge_point=point, score=score, max_score=max_score)

        profile = ProfileService().get_profile(PROFILE_A, db)
        assert "强项A" in profile.strengths
        assert "强项B" in profile.strengths
        assert "弱项" in profile.weaknesses
        assert "中等" not in profile.strengths
        assert "中等" not in profile.weaknesses

    def test_unknown_profile_is_empty(self, db: Session) -> None:
        profile = ProfileService().get_profile(PROFILE_B, db)
        assert profile.profile_id == PROFILE_B
        assert profile.mastery == []
        assert profile.strengths == []
        assert profile.weaknesses == []
        assert profile.confusion == []

    def test_confusion_aggregates_open_marks(self, db: Session) -> None:
        _add_mark(db, knowledge_point="集合", source_ref="explain:集合", source_type="explain")
        _add_mark(
            db,
            knowledge_point="集合",
            source_ref="quiz_question:q1",
            source_type="quiz_question",
            session_id="sess-b",
        )
        _add_mark(db, knowledge_point="函数", source_ref="explain:函数", source_type="explain")
        # An understood mark must not appear in 待复习.
        _add_mark(db, knowledge_point="概率", source_ref="ppt_page:概率:0", status="understood")

        profile = ProfileService().get_profile(PROFILE_A, db)
        by_point = {c.knowledge_point: c for c in profile.confusion}
        assert by_point["集合"].mark_count == 2
        assert set(by_point["集合"].source_types) == {"explain", "quiz_question"}
        assert by_point["函数"].mark_count == 1
        assert "概率" not in by_point


# ---------------------------------------------------------------------------
# Service: set_mark binary toggle
# ---------------------------------------------------------------------------


class TestSetMark:
    def _service(self) -> ProfileService:
        return ProfileService()

    def test_mark_confused(self, db: Session) -> None:
        resp = self._service().set_mark(
            MarkRequest(
                session_id="sess-a",
                profile_id=PROFILE_A,
                knowledge_point="集合",
                source_type="explain",
                source_ref="explain:集合",
                mark=True,
            ),
            db,
        )
        assert resp.status == "confused"
        rows = db.query(ConfusionMarkModel).all()
        assert len(rows) == 1
        assert rows[0].status == "confused"

    def test_mark_understood_clears_confusion(self, db: Session) -> None:
        svc = self._service()
        svc.set_mark(
            MarkRequest(
                session_id="sess-a",
                profile_id=PROFILE_A,
                knowledge_point="集合",
                source_type="explain",
                source_ref="explain:集合",
                mark=True,
            ),
            db,
        )
        svc.set_mark(
            MarkRequest(
                session_id="sess-a",
                profile_id=PROFILE_A,
                knowledge_point="集合",
                source_type="explain",
                source_ref="explain:集合",
                mark=False,
            ),
            db,
        )
        # Same row, toggled to understood — removed from the 待复习 list.
        rows = db.query(ConfusionMarkModel).all()
        assert len(rows) == 1
        assert rows[0].status == "understood"
        profile = svc.get_profile(PROFILE_A, db)
        assert profile.confusion == []

    def test_toggle_is_idempotent_on_source_ref(self, db: Session) -> None:
        svc = self._service()
        for _ in range(3):
            svc.set_mark(
                MarkRequest(
                    session_id="sess-a",
                    profile_id=PROFILE_A,
                    knowledge_point="集合",
                    source_type="explain",
                    source_ref="explain:集合",
                    mark=True,
                ),
                db,
            )
        assert db.query(ConfusionMarkModel).count() == 1

    def test_understood_without_existing_mark_is_noop(self, db: Session) -> None:
        resp = self._service().set_mark(
            MarkRequest(
                session_id="sess-a",
                profile_id=PROFILE_A,
                knowledge_point="集合",
                source_type="explain",
                source_ref="explain:集合",
                mark=False,
            ),
            db,
        )
        assert resp.status == "understood"
        assert db.query(ConfusionMarkModel).count() == 0

    def test_mark_without_profile_id_stays_out_of_portrait(self, db: Session) -> None:
        self._service().set_mark(
            MarkRequest(
                session_id="sess-a",
                profile_id=None,
                knowledge_point="集合",
                source_type="explain",
                source_ref="explain:集合",
                mark=True,
            ),
            db,
        )
        profile = self._service().get_profile(PROFILE_A, db)
        assert profile.confusion == []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class TestProfileEndpoints:
    def test_marks_endpoint_toggles(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/marks",
            json={
                "session_id": "sess-a",
                "profile_id": PROFILE_A,
                "knowledge_point": "集合",
                "source_type": "explain",
                "source_ref": "explain:集合",
                "mark": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confused"
        assert data["source_ref"] == "explain:集合"

    def test_marks_rejects_unknown_source_type(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/marks",
            json={
                "session_id": "sess-a",
                "knowledge_point": "集合",
                "source_type": "bogus",
                "source_ref": "x",
                "mark": True,
            },
        )
        assert resp.status_code == 422

    def test_profile_valid_uuid_returns_empty_200(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/profile?profile_id={PROFILE_B}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["profile_id"] == PROFILE_B
        assert data["mastery"] == []
        assert data["confusion"] == []

    def test_profile_invalid_uuid_is_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/profile?profile_id=not-a-uuid")
        assert resp.status_code == 422

    def test_profile_missing_uuid_is_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/profile")
        assert resp.status_code == 422

    def test_profile_returns_marks_after_toggle(self, client: TestClient) -> None:
        client.post(
            "/api/v1/learning/marks",
            json={
                "session_id": "sess-a",
                "profile_id": PROFILE_A,
                "knowledge_point": "集合",
                "source_type": "quiz_question",
                "source_ref": "quiz_question:集合:q1",
                "mark": True,
            },
        )
        resp = client.get(f"/api/v1/profile?profile_id={PROFILE_A}")
        assert resp.status_code == 200
        confusion = resp.json()["confusion"]
        assert len(confusion) == 1
        assert confusion[0]["knowledge_point"] == "集合"
        assert confusion[0]["source_types"] == ["quiz_question"]


class TestGradeToProfileFlow:
    """End-to-end: generate → grade with a profile_id → portrait reflects it."""

    def test_graded_single_and_fill_blank_land_in_portrait(
        self, client: TestClient
    ) -> None:
        gen = client.post(
            "/api/v1/learning/quiz/generate",
            json={"knowledge_point": "集合", "session_id": "sess-flow"},
        )
        assert gen.status_code == 200
        quiz = gen.json()

        grade = client.post(
            "/api/v1/learning/quiz/grade",
            json={
                "session_id": "sess-flow",
                "quiz_id": quiz["quiz_id"],
                "attempt_id": ATTEMPT_ID,
                "profile_id": PROFILE_A,
                "student_answers": [
                    {"question_id": "q1", "answer": ["B"]},  # single, correct
                    {"question_id": "q2", "answer": ["3"]},  # fill_blank, correct
                ],
            },
        )
        assert grade.status_code == 200
        data = grade.json()
        assert data["attempt_id"] == ATTEMPT_ID

        profile = client.get(f"/api/v1/profile?profile_id={PROFILE_A}")
        assert profile.status_code == 200
        mastery = profile.json()["mastery"]
        assert len(mastery) == 1
        entry = mastery[0]
        assert entry["knowledge_point"] == "集合"
        assert entry["sample_size"] == 2  # single (rules) + fill_blank (mock)
        assert entry["status"] == "insufficient"  # < MIN_MASTERY_SAMPLE

    def test_repeated_grade_with_same_attempt_id_is_idempotent(
        self, client: TestClient
    ) -> None:
        gen = client.post(
            "/api/v1/learning/quiz/generate",
            json={"knowledge_point": "函数", "session_id": "sess-idem"},
        )
        quiz = gen.json()
        payload = {
            "session_id": "sess-idem",
            "quiz_id": quiz["quiz_id"],
            "attempt_id": ATTEMPT_ID,
            "profile_id": PROFILE_A,
            "student_answers": [{"question_id": "q1", "answer": ["B"]}],
        }
        first = client.post("/api/v1/learning/quiz/grade", json=payload)
        second = client.post("/api/v1/learning/quiz/grade", json=payload)
        assert first.status_code == second.status_code == 200

        from code_navi.db import SessionLocal

        session = SessionLocal()
        try:
            rows = (
                session.query(QuizAttemptModel)
                .filter(QuizAttemptModel.attempt_id == ATTEMPT_ID)
                .all()
            )
            assert len(rows) == 1  # unique (attempt_id, question_id) prevented dup
        finally:
            session.close()

    def test_grade_without_profile_id_stays_out_of_portrait(
        self, client: TestClient
    ) -> None:
        gen = client.post(
            "/api/v1/learning/quiz/generate",
            json={"knowledge_point": "集合", "session_id": "sess-noprofile"},
        )
        quiz = gen.json()
        client.post(
            "/api/v1/learning/quiz/grade",
            json={
                "session_id": "sess-noprofile",
                "quiz_id": quiz["quiz_id"],
                "attempt_id": ATTEMPT_ID,
                "student_answers": [{"question_id": "q1", "answer": ["B"]}],
            },
        )
        profile = client.get(f"/api/v1/profile?profile_id={PROFILE_A}")
        assert profile.json()["mastery"] == []

    def test_generator_service_grades_and_persists(self, db: Session) -> None:
        """Service-level: a graded attempt row carries the profile_id for the portrait."""
        gen = QuizGenerator()
        quiz = gen.generate(
            QuizGenerateRequest(knowledge_point="排列组合", session_id="sess-svc"),
            db,
        )
        gen.grade_quiz(
            GradeRequest(
                session_id="sess-svc",
                quiz_id=quiz.quiz_id,
                attempt_id=ATTEMPT_ID,
                profile_id=PROFILE_A,
                student_answers=[StudentAnswerItem(question_id="q1", answer=["B"])],
            ),
            db,
        )
        row = (
            db.query(QuizAttemptModel)
            .filter(QuizAttemptModel.attempt_id == ATTEMPT_ID)
            .first()
        )
        assert row is not None
        assert row.profile_id == PROFILE_A
        assert row.graded_by == "rules"
        assert row.knowledge_point == "排列组合"
