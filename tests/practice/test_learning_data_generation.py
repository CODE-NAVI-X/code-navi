"""End-to-end coverage for Issue #85 learning-data practice generation."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.learning_profile.models import QuizAttemptModel  # noqa: E402
from code_navi.practice import router as practice_router  # noqa: E402
from code_navi.practice.models import PracticeSetModel  # noqa: E402
from code_navi.server import app  # noqa: E402

PROFILE_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture(autouse=True)
def _fresh_tables(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("CODE_NAVI_PRACTICE_PROVIDER", "mock")
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
    with TestClient(app) as test_client:
        yield test_client


def _add_weak_attempts(db: Session, topic: str = "network security") -> None:
    for index in range(3):
        db.add(
            QuizAttemptModel(
                attempt_id=str(uuid4()),
                quiz_id="quiz-learning-data",
                session_id="learning-session",
                knowledge_point=topic,
                profile_id=PROFILE_ID,
                user_id="local-user",
                question_id=f"question-{index}",
                question_type="single",
                points=10,
                score=0,
                max_score=10,
                correct=False,
                graded=True,
                graded_by="rules",
                is_mock=False,
                comment="Incorrect answer",
            )
        )
    db.commit()


def _request_body() -> dict[str, object]:
    return {
        "local_profile_id": "browser-profile",
        "profile_id": PROFILE_ID,
        "kind": "mixed",
        "count": 5,
        "difficulty": "medium",
    }


def test_generates_safe_archived_set_from_weakness_and_detects_bank_gap(
    client: TestClient, db: Session
) -> None:
    _add_weak_attempts(db)

    response = client.post("/api/v1/practice/sets/generate-from-learning", json=_request_body())

    assert response.status_code == 200
    data = response.json()
    assert data["generation_version"] == "learning-data.v1"
    assert data["selected_knowledge_points"] == ["network security"]
    assert data["question_bank_gaps"] == ["network security"]
    practice_set = data["practice_set"]
    assert practice_set["coverage"] == ["network security"]
    assert {item["item_kind"] for item in practice_set["items"]} == {
        "concept_quiz_question",
        "code_fill",
    }
    assert "answer" not in response.text
    assert "judge_secret" not in response.text

    archived = db.get(PracticeSetModel, practice_set["set_id"])
    assert archived is not None
    assert archived.local_profile_id == "browser-profile"
    assert archived.context_snapshot["learning_generation"]["version"] == "learning-data.v1"


def test_rejects_duplicate_learning_snapshot(client: TestClient, db: Session) -> None:
    _add_weak_attempts(db)
    first = client.post("/api/v1/practice/sets/generate-from-learning", json=_request_body())
    assert first.status_code == 200

    duplicate = client.post("/api/v1/practice/sets/generate-from-learning", json=_request_body())

    assert duplicate.status_code == 409
    assert "equivalent" in duplicate.json()["detail"]


def test_requires_traceable_learning_data(client: TestClient) -> None:
    response = client.post("/api/v1/practice/sets/generate-from-learning", json=_request_body())

    assert response.status_code == 409
    assert "No weak knowledge points" in response.json()["detail"]


def test_accepts_an_explicit_knowledge_point_without_fabricating_mastery(
    client: TestClient,
) -> None:
    body = _request_body() | {"knowledge_points": ["network security"]}

    response = client.post("/api/v1/practice/sets/generate-from-learning", json=body)

    assert response.status_code == 200
    data = response.json()
    assert data["selected_knowledge_points"] == ["network security"]
    context = data["practice_set"]["effective_context"]
    assert context["knowledge_points"][0]["mastery"] is None


def test_returns_explicit_failure_when_real_provider_fails(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_weak_attempts(db)
    monkeypatch.setenv("CODE_NAVI_PRACTICE_PROVIDER", "deepseek")

    def _fail_agent(**_kwargs: object) -> object:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(practice_router._practice_service, "_run_agent", _fail_agent)
    response = client.post("/api/v1/practice/sets/generate-from-learning", json=_request_body())

    assert response.status_code == 503
    assert "AI practice generator" in response.json()["detail"]
    assert db.query(PracticeSetModel).count() == 0


def test_rejects_sensitive_model_output_before_archiving(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_weak_attempts(db)
    monkeypatch.setenv("CODE_NAVI_PRACTICE_PROVIDER", "deepseek")
    credential_like = "sk-" + "x" * 26
    generated = {
        "items": [
            {
                "title": "unsafe item",
                "reference_code": f'token = "{credential_like}"',
                "code_masked": "token = ______",
                "blanks": [
                    {"blank_id": "one", "answer": "x", "hint": "first", "step_no": 1},
                    {"blank_id": "two", "answer": "y", "hint": "second", "step_no": 1},
                ],
                "steps": [{"step_no": 1, "title": "step", "reason": "reason"}],
            },
            {
                "title": "unsafe item two",
                "reference_code": f'token = "{credential_like}"',
                "code_masked": "token = ______",
                "blanks": [
                    {"blank_id": "one", "answer": "x", "hint": "first", "step_no": 1},
                    {"blank_id": "two", "answer": "y", "hint": "second", "step_no": 1},
                ],
                "steps": [{"step_no": 1, "title": "step", "reason": "reason"}],
            },
            {
                "title": "unsafe item three",
                "reference_code": f'token = "{credential_like}"',
                "code_masked": "token = ______",
                "blanks": [
                    {"blank_id": "one", "answer": "x", "hint": "first", "step_no": 1},
                    {"blank_id": "two", "answer": "y", "hint": "second", "step_no": 1},
                ],
                "steps": [{"step_no": 1, "title": "step", "reason": "reason"}],
            },
        ]
    }
    monkeypatch.setattr(
        practice_router._practice_service,
        "_run_agent",
        lambda **_kwargs: (SimpleNamespace(output_text=json.dumps(generated)), "deepseek"),
    )

    response = client.post("/api/v1/practice/sets/generate-from-learning", json=_request_body())

    assert response.status_code == 503
    assert db.query(PracticeSetModel).count() == 0
