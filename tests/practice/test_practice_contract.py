"""Contract tests for the practice gateway skeleton (Issue #43, S1).

These tests freeze the §1.1/§1.2/§1.3 response shapes of
``docs/specs/hands-on-practice-research-guidance-interfaces.md``: any schema
drift turns CI red (rollout plan §3 gate).  They also prove the answer-secrecy
invariant — ``judge_secret`` and ``blanks[].answer`` never cross the API
boundary on any path.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Force in-memory SQLite *before* any code_navi imports execute.
os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.practice.models import (  # noqa: E402
    CodeFillAttemptModel,
    PracticeSetItemModel,
    PracticeSetModel,
)
from code_navi.practice.schemas import PracticeSetGenerateRequest  # noqa: E402
from code_navi.practice.service import (  # noqa: E402
    PracticeSetNotFoundError,
    PracticeSetService,
)
from code_navi.server import app  # noqa: E402

#: Envelope keys a PracticeItem may expose (contract §1.1 + §1.2 grading hint).
_ENVELOPE_KEYS = {
    "item_id",
    "position",
    "item_kind",
    "knowledge_points",
    "judging",
    "payload",
    "grading_hint",
}
_CODE_FILL_SPEC_KEYS = {
    "title",
    "language",
    "complexity",
    "judge_mode",
    "code_masked",
    "blanks",
    "steps",
    "source",
    "reference_code_hash",
}
_CODE_FILL_BLANK_PUBLIC_KEYS = {"blank_id", "hint", "step_no"}
_CODING_PROBLEM_KEYS = {
    "id",
    "source",
    "title",
    "description",
    "difficulty",
    "tags",
    "starterCode",
    "inputHint",
    "outputHint",
    "sampleTests",
    "judgeable",
    "generationReason",
    "limitations",
}
_CONCEPT_PUBLIC_KEYS = {"id", "type", "question", "options", "points", "source"}


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
# Request validation (§1.2 校验)
# ---------------------------------------------------------------------------


class TestGenerateValidation:
    def test_empty_request_rejected_with_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/practice/sets/generate", json={})

        assert response.status_code == 422
        assert "生成依据" in response.json()["detail"]

    def test_kind_concept_requires_topic_or_context(self, client: TestClient) -> None:
        """upload_ids alone cannot drive a concept set: no knowledge point."""
        response = client.post(
            "/api/v1/practice/sets/generate",
            json={"kind": "concept_quiz", "upload_ids": ["upload-1"]},
        )

        assert response.status_code == 422
        assert "生成依据" in response.json()["detail"]

    def test_count_out_of_bounds_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/practice/sets/generate",
            json={"topic": "动态规划", "count": 9},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Mock closed loop: generate → archive → GET restore (§1.2 mock / §1.3)
# ---------------------------------------------------------------------------


class TestMockGenerateAndRestore:
    @pytest.mark.parametrize(
        ("kind", "expected_item_kinds"),
        [
            ("concept_quiz", {"concept_quiz_question"}),
            ("code_practice", {"code_fill", "coding_problem"}),
            ("mixed", {"concept_quiz_question", "code_fill"}),
        ],
    )
    def test_roundtrip_by_kind(
        self, client: TestClient, kind: str, expected_item_kinds: set[str]
    ) -> None:
        body = {"kind": kind, "topic": "动态规划", "count": 5}
        generated = client.post("/api/v1/practice/sets/generate", json=body)
        assert generated.status_code == 200, generated.text
        payload = generated.json()

        assert payload["kind"] == kind
        assert payload["generation_mode"] == "mock"
        assert payload["provider_name"] == "mock"
        assert payload["audit"] is None
        assert payload["effective_context"] is None
        assert payload["effective_topic"] == "动态规划"
        assert payload["coverage"] == ["动态规划"]
        assert len(payload["items"]) == 5
        assert {item["item_kind"] for item in payload["items"]} == expected_item_kinds
        for position, item in enumerate(payload["items"], start=1):
            assert item["position"] == position

        restored = client.get(f"/api/v1/practice/sets/{payload['set_id']}")
        assert restored.status_code == 200
        assert restored.json() == payload

    def test_context_driven_request_rejects_unrelated_mock_exercises(
        self, client: TestClient
    ) -> None:
        context = {
            "source_session_id": "sess-ctx-1",
            "knowledge_points": [
                {"name": "二叉树遍历", "source_ref": "notebook-1", "mastery": 0.4}
            ],
            "objective": "掌握二叉树的先序与中序遍历",
            "notes_summary": None,
        }
        generated = client.post(
            "/api/v1/practice/sets/generate",
            json={"kind": "mixed", "context": context, "count": 3},
        )
        assert generated.status_code == 409, generated.text
        assert "离线 Mock 模式" in generated.json()["detail"]
        assert "二叉树遍历" in generated.json()["detail"]

    def test_mixed_honours_concept_ratio(self, client: TestClient) -> None:
        generated = client.post(
            "/api/v1/practice/sets/generate",
            json={"kind": "mixed", "topic": "排序算法", "count": 4, "concept_ratio": 0.5},
        )
        assert generated.status_code == 200
        kinds = [item["item_kind"] for item in generated.json()["items"]]
        assert kinds.count("concept_quiz_question") == 2

    def test_get_unknown_set_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/practice/sets/00000000-0000-4000-8000-000000000000")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Answer secrecy (§0.6): judge_secret / blanks[].answer never in responses
# ---------------------------------------------------------------------------


class TestAnswerSecrecy:
    @pytest.mark.parametrize("kind", ["concept_quiz", "code_practice", "mixed"])
    def test_no_secret_fields_in_generate_response(
        self, client: TestClient, kind: str
    ) -> None:
        response = client.post(
            "/api/v1/practice/sets/generate", json={"kind": kind, "topic": "动态规划"}
        )
        assert response.status_code == 200
        raw = response.text
        payload = response.json()

        assert "judge_secret" not in raw
        for item in payload["items"]:
            self._assert_no_grading_material(item)

    def test_no_secret_fields_in_get_response(self, client: TestClient) -> None:
        set_id = client.post(
            "/api/v1/practice/sets/generate", json={"kind": "code_practice", "topic": "递归"}
        ).json()["set_id"]

        response = client.get(f"/api/v1/practice/sets/{set_id}")
        assert response.status_code == 200
        assert "judge_secret" not in response.text
        for item in response.json()["items"]:
            self._assert_no_grading_material(item)

    @staticmethod
    def _assert_no_grading_material(item: dict) -> None:
        assert "judge_secret" not in item
        if item["item_kind"] == "code_fill":
            for blank in item["payload"]["blanks"]:
                assert "answer" not in blank
                assert "alternate_answers" not in blank
        elif item["item_kind"] == "concept_quiz_question":
            assert "answer" not in item["payload"]
            assert "analysis" not in item["payload"]


# ---------------------------------------------------------------------------
# Response shape frozen against the contract (§1.1 envelope + payloads)
# ---------------------------------------------------------------------------


class TestResponseShape:
    @pytest.mark.parametrize(
        ("kind", "expected_judging"),
        [
            ("concept_quiz", "rules_llm"),
            ("code_practice", {"llm_static", "server_tests"}),
            ("mixed", {"rules_llm", "llm_static"}),
        ],
    )
    def test_judging_channel_mapping(
        self, client: TestClient, kind: str, expected_judging: str | set[str]
    ) -> None:
        payload = client.post(
            "/api/v1/practice/sets/generate", json={"kind": kind, "topic": "图论"}
        ).json()

        judging = {item["judging"] for item in payload["items"]}
        if kind == "concept_quiz":
            assert judging == {expected_judging}
        else:
            assert judging == expected_judging

    def test_concept_items_hint_quiz_grade_channel(self, client: TestClient) -> None:
        payload = client.post(
            "/api/v1/practice/sets/generate", json={"kind": "mixed", "topic": "图论"}
        ).json()

        for item in payload["items"]:
            if item["item_kind"] == "concept_quiz_question":
                assert item["grading_hint"] == "/learning/quiz/grade"
            else:
                assert item["grading_hint"] is None

    def test_item_payloads_match_contract_shapes(self, client: TestClient) -> None:
        payload = client.post(
            "/api/v1/practice/sets/generate",
            json={"kind": "mixed", "topic": "二分查找", "count": 5},
        ).json()

        assert len(payload["items"]) == 5
        for item in payload["items"]:
            assert set(item.keys()) == _ENVELOPE_KEYS
            assert len(item["knowledge_points"]) <= 4
            assert item["payload"], "payload must not be empty"
            if item["item_kind"] == "concept_quiz_question":
                assert _CONCEPT_PUBLIC_KEYS <= set(item["payload"].keys())
                assert item["payload"]["type"] == "single"
                assert {option["value"] for option in item["payload"]["options"]} == {
                    "A",
                    "B",
                    "C",
                    "D",
                }
            elif item["item_kind"] == "coding_problem":
                assert set(item["payload"].keys()) == _CODING_PROBLEM_KEYS
                assert item["payload"]["judgeable"] is True
            else:
                assert set(item["payload"].keys()) == _CODE_FILL_SPEC_KEYS
                assert item["payload"]["language"] == "python"
                assert item["payload"]["complexity"] == "light"
                assert item["payload"]["judge_mode"] == "llm_static"
                blanks = item["payload"]["blanks"]
                assert 2 <= len(blanks) <= 6
                for blank in blanks:
                    assert set(blank.keys()) == _CODE_FILL_BLANK_PUBLIC_KEYS
                assert 1 <= len(item["payload"]["steps"]) <= 5
                assert "______" in item["payload"]["code_masked"]
                assert item["payload"]["reference_code_hash"]


# ---------------------------------------------------------------------------
# Storage layer invariants (§1.1 表格)
# ---------------------------------------------------------------------------


def _seed_set(db: Session, set_id: str) -> None:
    """Insert a parent set row so item/attempt FKs point at a real set."""
    db.add(
        PracticeSetModel(
            set_id=set_id,
            kind="code_practice",
            generation_mode="mock",
            provider_name="mock",
        )
    )
    db.commit()


class TestStorageInvariants:
    def test_judge_secret_holds_quiz_session_ref_structure(self, db: Session) -> None:
        """judge_secret must be able to carry the P1-A mixed-archive reference."""
        _seed_set(db, "set-0001")
        item = PracticeSetItemModel(
            set_id="set-0001",
            item_id="item-01",
            position=1,
            item_kind="concept_quiz_question",
            payload={"id": "item-01"},
            judge_secret={"quiz_session_ref": "set-0001"},
        )
        db.add(item)
        db.commit()

        stored = db.query(PracticeSetItemModel).one()
        assert stored.judge_secret == {"quiz_session_ref": "set-0001"}

    def test_code_fill_attempts_unique_per_attempt_and_item(self, db: Session) -> None:
        """The composite (attempt_id, item_id) key realizes the contract UNIQUE."""
        _seed_set(db, "set-0001")
        db.add(CodeFillAttemptModel(attempt_id="a-1", item_id="item-01", set_id="set-0001"))
        db.add(CodeFillAttemptModel(attempt_id="a-1", item_id="item-02", set_id="set-0001"))
        db.commit()

        db.add(CodeFillAttemptModel(attempt_id="a-1", item_id="item-01", set_id="set-0001"))
        with pytest.raises(IntegrityError):
            db.commit()


# ---------------------------------------------------------------------------
# Owner filtering (§0.1, service level — no login plumbing needed)
# ---------------------------------------------------------------------------


class TestOwnerFiltering:
    def test_cross_owner_set_is_hidden(self, db: Session) -> None:
        service = PracticeSetService()
        generated = service.generate(
            _request(topic="动态规划"), db, owner_principal_id="principal-A"
        )

        assert service.get_set(db, generated.set_id, owned_ids=["principal-A"]).set_id
        with pytest.raises(PracticeSetNotFoundError):
            service.get_set(db, generated.set_id, owned_ids=["principal-B"])

    def test_authenticated_user_does_not_see_anonymous_sets(self, db: Session) -> None:
        service = PracticeSetService()
        generated = service.generate(_request(topic="动态规划"), db, owner_principal_id=None)

        with pytest.raises(PracticeSetNotFoundError):
            service.get_set(db, generated.set_id, owned_ids=["principal-A"])
        # Anonymous callers stay unfiltered during the compat period.
        assert service.get_set(db, generated.set_id, owned_ids=None).set_id

    def test_unknown_set_id_raises_not_found(self, db: Session) -> None:
        with pytest.raises(PracticeSetNotFoundError):
            PracticeSetService().get_set(db, "missing-set", owned_ids=None)


def _request(topic: str) -> PracticeSetGenerateRequest:
    return PracticeSetGenerateRequest(kind="code_practice", topic=topic, count=3)
