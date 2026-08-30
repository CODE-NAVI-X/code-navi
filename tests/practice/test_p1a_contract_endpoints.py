"""P1-A contract tests for grading, upload analysis, explain-symbol and mixed
double-write.

These tests cover the review defects from PR #52 without changing the frozen S1
mock-generation contract: the existing ``test_practice_contract.py`` remains the
authority for §1.1–1.3 shapes.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.practice.models import (  # noqa: E402
    PracticeSetItemModel,
    PracticeSetModel,
)
from code_navi.practice.schemas import CodeFillGradeRequest  # noqa: E402
from code_navi.practice.service import (  # noqa: E402
    PracticeSetNotFoundError,
    PracticeSetService,
)
from code_navi.server import app  # noqa: E402


def _attempt_id() -> str:
    return str(uuid4())


def _correct_answers() -> list[dict[str, str]]:
    return [
        {"blank_id": "blank-1", "value": "total + value"},
        {"blank_id": "blank-2", "value": "len(nums)"},
    ]


def _generate_mixed(client: TestClient) -> tuple[str, str, str]:
    response = client.post(
        "/api/v1/practice/sets/generate",
        json={"kind": "mixed", "topic": "循环", "count": 3},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    concept = next(
        item for item in payload["items"] if item["item_kind"] == "concept_quiz_question"
    )
    code_fill = next(item for item in payload["items"] if item["item_kind"] == "code_fill")
    return payload["set_id"], concept["item_id"], code_fill["item_id"]


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
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


class TestCodeFillGrade:
    def test_correct_and_wrong_answers_are_judged_rules(
        self, client: TestClient
    ) -> None:
        set_id, _, item_id = _generate_mixed(client)

        correct = client.post(
            "/api/v1/practice/code-fill/grade",
            json={
                "set_id": set_id,
                "item_id": item_id,
                "attempt_id": _attempt_id(),
                "blank_answers": _correct_answers(),
            },
        )
        assert correct.status_code == 200, correct.text
        correct_body = correct.json()
        assert correct_body["total_score"] == 2
        assert correct_body["total_max_score"] == 2
        assert correct_body["graded"] is True
        assert correct_body["is_mock"] is False
        assert all(item["correct"] for item in correct_body["results"])
        assert all(item["graded_by"] == "rules" for item in correct_body["results"])

        wrong = client.post(
            "/api/v1/practice/code-fill/grade",
            json={
                "set_id": set_id,
                "item_id": item_id,
                "attempt_id": _attempt_id(),
                "blank_answers": [
                    {"blank_id": "blank-1", "value": "x"},
                    {"blank_id": "blank-2", "value": "y"},
                ],
            },
        )
        assert wrong.status_code == 200, wrong.text
        wrong_body = wrong.json()
        assert wrong_body["total_score"] == 0
        assert wrong_body["graded"] is True
        assert all(not item["correct"] for item in wrong_body["results"])
        assert all(item["graded_by"] == "rules" for item in wrong_body["results"])

    def test_repeat_attempt_id_is_idempotent(self, client: TestClient) -> None:
        set_id, _, item_id = _generate_mixed(client)
        attempt_id = _attempt_id()
        payload = {
            "set_id": set_id,
            "item_id": item_id,
            "attempt_id": attempt_id,
            "blank_answers": _correct_answers(),
        }

        first = client.post("/api/v1/practice/code-fill/grade", json=payload)
        second = client.post("/api/v1/practice/code-fill/grade", json=payload)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert second.json() == first.json()

    def test_cross_owner_item_is_404(self, db: Session) -> None:
        service = PracticeSetService()
        generated = service.generate(
            _request("循环"),
            db,
            owner_principal_id="principal-A",
        )
        code_fill_item = next(
            item for item in generated.items if item.item_kind == "code_fill"
        )
        grade = CodeFillGradeRequest(
            set_id=generated.set_id,
            item_id=code_fill_item.item_id,
            attempt_id=_attempt_id(),
            blank_answers=_correct_answers(),
        )

        assert service.grade_code_fill(
            grade, db, owner_principal_id="principal-A", owned_ids=["principal-A"]
        ).attempt_id
        with pytest.raises(PracticeSetNotFoundError):
            service.grade_code_fill(
                grade,
                db,
                owner_principal_id="principal-B",
                owned_ids=["principal-B"],
            )

    def test_explain_only_item_returns_409(self, client: TestClient, db: Session) -> None:
        set_id = "set-explain-only"
        item_id = "item-explain-only"
        db.add(
            PracticeSetModel(
                set_id=set_id,
                kind="code_practice",
                generation_mode="mock",
                provider_name="mock",
            )
        )
        db.add(
            PracticeSetItemModel(
                set_id=set_id,
                item_id=item_id,
                position=1,
                item_kind="code_fill",
                payload={"judge_mode": "explain_only"},
                judge_secret={"blanks": []},
            )
        )
        db.commit()

        response = client.post(
            "/api/v1/practice/code-fill/grade",
            json={
                "set_id": set_id,
                "item_id": item_id,
                "attempt_id": _attempt_id(),
                "blank_answers": [{"blank_id": "blank-1", "value": "x"}],
            },
        )

        assert response.status_code == 409
        assert "讲解型" in response.json()["detail"]


class TestCodeUploadAnalyze:
    def test_unsupported_suffix_returns_415(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/practice/code-uploads/analyze",
            json={"filename": "notes.txt", "content_base64": base64.b64encode(b"x").decode()},
        )

        assert response.status_code == 415

    def test_oversized_upload_returns_413(self, client: TestClient) -> None:
        content = base64.b64encode(b"a" * (256 * 1024 + 1)).decode()
        response = client.post(
            "/api/v1/practice/code-uploads/analyze",
            json={"filename": "big.py", "content_base64": content},
        )

        assert response.status_code == 413

    def test_dataset_traces_return_400(self, client: TestClient) -> None:
        content = base64.b64encode(b"import pickle\n").decode()
        response = client.post(
            "/api/v1/practice/code-uploads/analyze",
            json={"filename": "dataset.py", "content_base64": content},
        )

        assert response.status_code == 400
        assert "仅支持核心代码或文档文件" in response.json()["detail"]

    def test_valid_python_upload_is_persisted_and_usable(self, client: TestClient) -> None:
        source = "def average(nums):\n    return sum(nums) / len(nums)\n"
        analyzed = client.post(
            "/api/v1/practice/code-uploads/analyze",
            json={
                "filename": "average.py",
                "content_base64": base64.b64encode(source.encode()).decode(),
            },
        )
        assert analyzed.status_code == 200, analyzed.text
        upload = analyzed.json()
        assert upload["kind"] == "python"
        assert upload["upload_id"]

        generated = client.post(
            "/api/v1/practice/sets/generate",
            json={
                "kind": "code_practice",
                "topic": "循环",
                "upload_ids": [upload["upload_id"]],
            },
        )
        assert generated.status_code == 200, generated.text

        missing = client.post(
            "/api/v1/practice/sets/generate",
            json={"kind": "code_practice", "topic": "循环", "upload_ids": ["missing-upload"]},
        )
        assert missing.status_code == 404


class TestExplainSymbol:
    def test_explain_symbol_returns_200_and_caches(self, client: TestClient) -> None:
        set_id, _, item_id = _generate_mixed(client)
        payload = {
            "set_id": set_id,
            "item_id": item_id,
            "symbol": {
                "name": "average",
                "kind": "function",
                "code_excerpt": "def average(nums):\n    return sum(nums) / len(nums)",
            },
        }

        first = client.post("/api/v1/practice/code-fill/explain-symbol", json=payload)
        second = client.post("/api/v1/practice/code-fill/explain-symbol", json=payload)

        assert first.status_code == 200, first.text
        assert first.json()["source"] == "rules"
        assert first.json()["cached"] is False
        assert second.status_code == 200, second.text
        assert second.json()["cached"] is True


class TestMixedDoubleWrite:
    def test_concept_item_grades_via_learning_quiz(self, client: TestClient) -> None:
        set_id, concept_item_id, _ = _generate_mixed(client)

        response = client.post(
            "/api/v1/learning/quiz/grade",
            json={
                "session_id": set_id,
                "quiz_id": concept_item_id,
                "attempt_id": _attempt_id(),
                "student_answers": [
                    {"question_id": concept_item_id, "answer": ["A"]}
                ],
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["session_id"] == set_id
        assert body["results"][0]["is_correct"] is True
        assert body["total_score"] == 10


def _request(topic: str):
    from code_navi.practice.schemas import PracticeSetGenerateRequest

    return PracticeSetGenerateRequest(kind="code_practice", topic=topic, count=3)
