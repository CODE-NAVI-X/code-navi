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
from datetime import UTC, datetime, timedelta

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
from code_navi.learning_profile.schemas import MarkRequest, ProfileResponse  # noqa: E402
from code_navi.learning_profile.service import (  # noqa: E402
    ProfileService,
    build_student_profile_prompt,
)
from code_navi.online_compiler.models import (  # noqa: E402
    PracticeLaunchModel,
    PracticeOutcomeModel,
)
from code_navi.server import app  # noqa: E402
from code_navi.workspaces.models import WorkspaceModel  # noqa: E402

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
    created_at: datetime | None = None,
) -> None:
    attempt = QuizAttemptModel(
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
    if created_at is not None:
        attempt.created_at = created_at
    db.add(attempt)
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
    created_at: datetime | None = None,
) -> None:
    mark = ConfusionMarkModel(
        session_id=session_id,
        profile_id=profile_id,
        user_id=None,
        knowledge_point=knowledge_point,
        source_type=source_type,
        source_ref=source_ref,
        status=status,
    )
    if created_at is not None:
        mark.created_at = created_at
    db.add(mark)
    db.commit()


def _add_practice_outcome(
    db: Session,
    *,
    local_profile_id: str = "profile-owner",
    learner_id: str = PROFILE_A,
    focus_label: str = "循环调试",
    summary: str = "运行时错误：ZeroDivisionError",
    knowledge_gap_kind: str | None = "runtime_error",
) -> PracticeOutcomeModel:
    workspace = WorkspaceModel(
        owner_scope_id=local_profile_id,
        personal_owner_scope_id=None,
        title="Practice workspace",
        kind="general",
    )
    db.add(workspace)
    db.flush()
    launch = PracticeLaunchModel(
        local_profile_id=local_profile_id,
        learner_id=learner_id,
        workspace_id=workspace.id,
        task_id=None,
        source_activity_id=None,
        capability="practice",
        mode="free_run",
        focus_type="topic",
        focus_id="loop-debugging",
        focus_label=focus_label,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(launch)
    db.flush()
    outcome = PracticeOutcomeModel(
        launch_id=launch.id,
        local_profile_id=local_profile_id,
        learner_id=learner_id,
        workspace_id=workspace.id,
        task_id=None,
        mode="execute",
        idempotency_key=str(uuid.uuid4()),
        problem_id=None,
        problem_version=None,
        verdict="runtime_error",
        category="runtime_error",
        severity="error",
        score=None,
        summary=summary,
        safe_result_data=(
            '{"kind":"compiler_execute.v1","stdout":"secret stdout",'
            '"stderr":"secret stderr","source":"print(secret)","stdin":"private stdin"}'
        ),
        knowledge_gap_kind=knowledge_gap_kind,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return outcome


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
        assert set(by_point["集合"].by_type) == {"explain", "quiz_question"}
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
        assert set(confusion[0]["by_type"]) == {"quiz_question"}
        item = confusion[0]["by_type"]["quiz_question"][0]
        assert item["label"] == "quiz_question:集合:q1"  # falls back to source_ref


class TestKnowledgeGapProjection:
    def test_learning_knowledge_gaps_merges_traceable_sources(
        self, client: TestClient, db: Session
    ) -> None:
        _add_attempt(db, knowledge_point="集合", score=0, max_score=10)
        _add_mark(
            db,
            knowledge_point="函数",
            source_ref="explain:函数",
            source_type="explain",
            status="confused",
        )
        practice = _add_practice_outcome(db)

        response = client.get(
            "/api/v1/learning/knowledge-gaps"
            f"?local_profile_id=profile-owner&profile_id={PROFILE_A}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["localProfileId"] == "profile-owner"
        assert data["profileId"] == PROFILE_A
        items = data["items"]
        by_source = {item["sourceType"]: item for item in items}

        quiz = by_source["quiz_attempt"]
        assert quiz["sourceId"]
        assert quiz["topic"] == "集合"
        assert quiz["gapKind"] == "quiz_incorrect"
        assert quiz["source"]["score"] == 0
        assert quiz["source"]["maxScore"] == 10

        mark = by_source["confusion_mark"]
        assert mark["topic"] == "函数"
        assert mark["gapKind"] == "self_reported_confusion"
        assert mark["source"]["surfaceRef"] == "explain:函数"

        practice_item = by_source["practice_outcome"]
        assert practice_item["sourceId"] == practice.id
        assert practice_item["topic"] == "循环调试"
        assert practice_item["gapKind"] == "runtime_error"
        assert practice_item["source"]["workspaceId"] == practice.workspace_id

    def test_learning_knowledge_gaps_scopes_practice_by_local_profile(
        self, client: TestClient, db: Session
    ) -> None:
        _add_practice_outcome(db, local_profile_id="profile-owner", learner_id=PROFILE_A)
        _add_practice_outcome(
            db,
            local_profile_id="other-owner",
            learner_id=PROFILE_A,
            focus_label="不应显示",
        )

        response = client.get(
            "/api/v1/learning/knowledge-gaps"
            f"?local_profile_id=profile-owner&profile_id={PROFILE_A}"
        )

        assert response.status_code == 200
        practice_items = [
            item for item in response.json()["items"] if item["sourceType"] == "practice_outcome"
        ]
        assert len(practice_items) == 1
        assert practice_items[0]["topic"] == "循环调试"

    def test_learning_knowledge_gaps_does_not_return_practice_sensitive_fields(
        self, client: TestClient, db: Session
    ) -> None:
        _add_practice_outcome(db, summary="运行时错误摘要")

        response = client.get(
            "/api/v1/learning/knowledge-gaps"
            f"?local_profile_id=profile-owner&profile_id={PROFILE_A}"
        )

        assert response.status_code == 200
        body = response.text
        assert "secret stdout" not in body
        assert "secret stderr" not in body
        assert "print(secret)" not in body
        assert "private stdin" not in body
        assert "运行时错误摘要" in body

    def test_learning_knowledge_gaps_invalid_profile_id_is_422(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/api/v1/learning/knowledge-gaps"
            "?local_profile_id=profile-owner&profile_id=not-a-uuid"
        )
        assert response.status_code == 422


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


# ---------------------------------------------------------------------------
# M2: normalized grouping (UDP/udp), by_type columns, profile-level 已懂
# ---------------------------------------------------------------------------


class TestNormalizedGrouping:
    """Same knowledge point written differently collapses into one group."""

    def test_mastery_normalizes_case_and_keeps_first_seen_spelling(
        self, db: Session
    ) -> None:
        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        _add_attempt(db, knowledge_point="UDP", score=10, max_score=10, created_at=t0)
        _add_attempt(
            db,
            knowledge_point="udp",
            score=6,
            max_score=10,
            created_at=t0 + timedelta(seconds=1),
        )
        _add_attempt(
            db,
            knowledge_point="UDP",
            score=8,
            max_score=10,
            created_at=t0 + timedelta(seconds=2),
        )

        profile = ProfileService().get_profile(PROFILE_A, db)
        assert len(profile.mastery) == 1
        entry = profile.mastery[0]
        # Display name is the first-seen original spelling, not the lowercase key.
        assert entry.knowledge_point == "UDP"
        assert entry.sample_size == 3
        assert entry.quiz_rate == pytest.approx(0.8)
        assert entry.mastery == pytest.approx(0.8)
        assert entry.status == "sufficient"

    def test_mastery_first_seen_spelling_depends_on_insert_order(
        self, db: Session
    ) -> None:
        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        _add_attempt(db, knowledge_point="udp", score=10, max_score=10, created_at=t0)
        _add_attempt(
            db,
            knowledge_point="UDP",
            score=10,
            max_score=10,
            created_at=t0 + timedelta(seconds=1),
        )

        profile = ProfileService().get_profile(PROFILE_A, db)
        assert len(profile.mastery) == 1
        assert profile.mastery[0].knowledge_point == "udp"

    def test_confusion_normalizes_case_and_dedupes_by_surface(
        self, db: Session
    ) -> None:
        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        _add_mark(
            db,
            knowledge_point="UDP",
            source_ref="explain:UDP",
            source_type="explain",
            created_at=t0,
        )
        # Same surface in another session must collapse into one 待复习 entry.
        _add_mark(
            db,
            knowledge_point="udp",
            source_ref="explain:UDP",
            source_type="explain",
            session_id="sess-b",
            created_at=t0 + timedelta(seconds=1),
        )
        _add_mark(
            db,
            knowledge_point="udp",
            source_ref="quiz_question:udp:q1",
            source_type="quiz_question",
            session_id="sess-c",
            created_at=t0 + timedelta(seconds=2),
        )

        profile = ProfileService().get_profile(PROFILE_A, db)
        assert len(profile.confusion) == 1
        item = profile.confusion[0]
        assert item.knowledge_point == "UDP"
        assert item.mark_count == 2  # distinct surfaces only
        assert set(item.by_type) == {"explain", "quiz_question"}
        explain_items = item.by_type["explain"]
        assert len(explain_items) == 1  # deduped across sessions
        assert explain_items[0].source_ref == "explain:UDP"
        assert explain_items[0].label == "explain:UDP"  # falls back to source_ref

    def test_confusion_by_type_uses_fixed_column_order(self, db: Session) -> None:
        _add_mark(
            db,
            knowledge_point="集合",
            source_ref="quiz_question:q1",
            source_type="quiz_question",
        )
        _add_mark(db, knowledge_point="集合", source_ref="explain:集合", source_type="explain")
        _add_mark(
            db,
            knowledge_point="集合",
            source_ref="ppt_page:集合:0",
            source_type="ppt_page",
        )

        profile = ProfileService().get_profile(PROFILE_A, db)
        assert list(profile.confusion[0].by_type) == ["ppt_page", "explain", "quiz_question"]


class TestMarkLabel:
    def test_mark_stores_label_for_portrait_display(self, db: Session) -> None:
        svc = ProfileService()
        svc.set_mark(
            MarkRequest(
                session_id="sess-a",
                profile_id=PROFILE_A,
                knowledge_point="集合",
                source_type="explain",
                source_ref="explain:集合",
                label="集合的列举法没看懂",
                mark=True,
            ),
            db,
        )
        row = db.query(ConfusionMarkModel).first()
        assert row is not None
        assert row.label == "集合的列举法没看懂"
        profile = svc.get_profile(PROFILE_A, db)
        item = profile.confusion[0].by_type["explain"][0]
        assert item.label == "集合的列举法没看懂"

    def test_understood_with_profile_id_clears_across_sessions(
        self, db: Session
    ) -> None:
        svc = ProfileService()
        for session in ("sess-a", "sess-b"):
            svc.set_mark(
                MarkRequest(
                    session_id=session,
                    profile_id=PROFILE_A,
                    knowledge_point="集合",
                    source_type="explain",
                    source_ref="explain:集合",
                    label="集合没看懂",
                    mark=True,
                ),
                db,
            )
        assert db.query(ConfusionMarkModel).count() == 2

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
        statuses = {row.status for row in db.query(ConfusionMarkModel).all()}
        assert statuses == {"understood"}
        assert svc.get_profile(PROFILE_A, db).confusion == []

    def test_understood_without_profile_id_is_per_session(
        self, db: Session
    ) -> None:
        """mark=False with no profile_id only flips the requesting session's row."""
        svc = ProfileService()
        for session in ("sess-a", "sess-b"):
            svc.set_mark(
                MarkRequest(
                    session_id=session,
                    profile_id=PROFILE_A,
                    knowledge_point="集合",
                    source_type="explain",
                    source_ref="explain:集合",
                    mark=True,
                ),
                db,
            )
        # No profile_id → the per-session toggle path; only sess-b's row flips.
        svc.set_mark(
            MarkRequest(
                session_id="sess-b",
                knowledge_point="集合",
                source_type="explain",
                source_ref="explain:集合",
                mark=False,
            ),
            db,
        )
        # sess-a's mark is still confused in the portrait → 1 item remains.
        profile = svc.get_profile(PROFILE_A, db)
        assert len(profile.confusion) == 1


class TestBuildStudentProfilePrompt:
    """The prompt injection segment — fact-boundary safe and deterministic."""

    def test_empty_portrait_yields_none(self) -> None:
        empty = ProfileResponse(
            profile_id=PROFILE_A,
            generated_at="2026-08-16T00:00:00+00:00",
            mastery=[],
            strengths=[],
            weaknesses=[],
            confusion=[],
        )
        assert build_student_profile_prompt(empty) is None

    def test_with_data_covers_strengths_weaknesses_and_review(
        self, db: Session
    ) -> None:
        for point, score in [("强项A", 10), ("强项B", 8)]:
            for _ in range(3):
                _add_attempt(db, knowledge_point=point, score=score, max_score=10)
        for _ in range(3):
            _add_attempt(db, knowledge_point="函数", score=1, max_score=10)
        _add_mark(db, knowledge_point="概率", source_ref="explain:概率", source_type="explain")

        prompt = build_student_profile_prompt(
            ProfileService().get_profile(PROFILE_A, db)
        )
        assert prompt is not None
        assert "学生真实学情画像" in prompt
        assert "已掌握较好" in prompt and "强项A" in prompt
        assert "需要加强" in prompt and "函数" in prompt
        assert "待复习" in prompt and "概率" in prompt

    def test_undersampled_reports_样本不足_without_fabricated_number(
        self, db: Session
    ) -> None:
        _add_attempt(db, knowledge_point="集合", score=8, max_score=10)
        _add_attempt(db, knowledge_point="集合", score=6, max_score=10)

        prompt = build_student_profile_prompt(
            ProfileService().get_profile(PROFILE_A, db)
        )
        assert prompt is not None
        assert "样本不足" in prompt
        # The real rate is 70% but the portrait refuses to report a mastery
        # value at 2 samples — the prompt must never paraphrase it as a number.
        assert "70%" not in prompt
        assert "0.7" not in prompt

    def test_only_confusion_marks_still_yield_a_prompt(self, db: Session) -> None:
        _add_mark(db, knowledge_point="概率", source_ref="explain:概率", source_type="explain")

        prompt = build_student_profile_prompt(
            ProfileService().get_profile(PROFILE_A, db)
        )
        assert prompt is not None
        assert "待复习" in prompt
        assert "概率" in prompt
