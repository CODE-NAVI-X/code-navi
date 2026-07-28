"""Unit tests for the learning module (persistence, decontamination, API endpoints).

All tests use ``sqlite:///:memory:`` — no filesystem side-effects and fully
repeatable.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Force in-memory SQLite *before* any code_navi.learning imports execute.
os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.learning.database import SessionLocal, engine  # noqa: E402
from code_navi.learning.models import Base, NotebookItemModel  # noqa: E402
from code_navi.learning.schemas import ExplainRequest  # noqa: E402
from code_navi.learning.services import (  # noqa: E402
    PromptDecontaminationEngine,
    QueryOrchestrator,
)
from code_navi.server import app  # noqa: E402


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
# 1.  Decontamination engine tests
# ---------------------------------------------------------------------------


class TestDecontaminationEngine:
    def test_decontaminate_preserves_core_content(self) -> None:
        engine_ = PromptDecontaminationEngine()
        result = engine_.decontaminate("TCP slow start algorithm")

        assert "TCP slow start algorithm" in result
        assert "[decontaminated]" in result
        assert engine_.passphrase in result

    def test_decontaminate_always_includes_guard_phrase(self) -> None:
        engine_ = PromptDecontaminationEngine()
        result = engine_.decontaminate("")

        assert "Guard:" in result
        assert engine_.passphrase in result


# ---------------------------------------------------------------------------
# 2.  Persistence (NotebookItemModel) tests
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_create_and_read_notebook_item(self, db: Session) -> None:
        item = NotebookItemModel(
            user_id="student-1",
            knowledge_id="kn:recursion",
            item_type="note",
            content="Base case + inductive step.",
            extra_data={"source": "textbook"},
        )
        db.add(item)
        db.commit()

        fetched = (
            db.query(NotebookItemModel)
            .filter_by(knowledge_id="kn:recursion")
            .first()
        )
        assert fetched is not None
        assert fetched.user_id == "student-1"
        assert fetched.item_type == "note"
        assert fetched.content == "Base case + inductive step."
        assert fetched.extra_data == {"source": "textbook"}
        assert fetched.created_at is not None

    def test_multiple_items_same_user(self, db: Session) -> None:
        db.add_all(
            [
                NotebookItemModel(
                    user_id="u1",
                    knowledge_id="k1",
                    item_type="summary",
                    content="Summary 1",
                ),
                NotebookItemModel(
                    user_id="u1",
                    knowledge_id="k2",
                    item_type="wrong_answer",
                    content="Answer 2",
                ),
            ]
        )
        db.commit()

        items = (
            db.query(NotebookItemModel).filter_by(user_id="u1").all()
        )
        assert len(items) == 2
        assert {i.item_type for i in items} == {"summary", "wrong_answer"}

    def test_extra_data_nullable(self, db: Session) -> None:
        item = NotebookItemModel(
            user_id="u1",
            knowledge_id="k1",
            item_type="summary",
            content="No extra data.",
        )
        db.add(item)
        db.commit()

        fetched = (
            db.query(NotebookItemModel).filter_by(knowledge_id="k1").first()
        )
        assert fetched is not None
        assert fetched.extra_data is None


# ---------------------------------------------------------------------------
# 3.  QueryOrchestrator integration tests
# ---------------------------------------------------------------------------


class TestQueryOrchestrator:
    def test_explain_without_api_key_uses_offline_stub(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("code_navi.learning.services.DEEPSEEK_API_KEY", "")

        response = QueryOrchestrator().explain(
            ExplainRequest(knowledge_point="offline learning"),
            db,
        )

        assert "[decontaminated]" in response.summary
        assert response.citations[0].source_title == "PoC stub citation"

    def test_explain_persists_to_notebook(self, db: Session) -> None:
        orchestrator = QueryOrchestrator()
        request = ExplainRequest(
            knowledge_point="Dijkstra's algorithm",
            persona="academic",
            include_citations=True,
        )

        response = orchestrator.explain(request, db)

        assert response.knowledge_point == "Dijkstra's algorithm"
        assert len(response.citations) == 1
        assert response.citations[0].source_title == "PoC stub citation"

        # Verify notebook persistence
        item = (
            db.query(NotebookItemModel)
            .filter_by(knowledge_id="Dijkstra's algorithm")
            .first()
        )
        assert item is not None
        assert item.item_type == "summary"
        assert item.content == response.summary

    def test_explain_without_citations(self, db: Session) -> None:
        orchestrator = QueryOrchestrator()
        request = ExplainRequest(
            knowledge_point="hash table",
            include_citations=False,
        )

        response = orchestrator.explain(request, db)
        assert response.citations == []

    def test_explain_decontaminates_query(self, db: Session) -> None:
        orchestrator = QueryOrchestrator()
        request = ExplainRequest(knowledge_point="Big-O notation")

        response = orchestrator.explain(request, db)

        assert "[decontaminated]" in response.summary
        assert orchestrator.decontamination_engine.passphrase in response.summary


# ---------------------------------------------------------------------------
# 4.  API endpoint tests
# ---------------------------------------------------------------------------


class TestExplainEndpoint:
    def test_post_explain_returns_200(self, client: TestClient) -> None:
        payload = {
            "knowledge_point": "Monad",
            "persona": "academic",
            "include_citations": True,
        }

        resp = client.post("/api/v1/learning/explain", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert body["knowledge_point"] == "Monad"
        assert body["summary"] is not None
        assert len(body["citations"]) == 1

    def test_post_explain_persists_across_requests(self, client: TestClient, db: Session) -> None:
        # First request
        client.post(
            "/api/v1/learning/explain",
            json={"knowledge_point": "currying"},
        )

        # Second request (different topic)
        client.post(
            "/api/v1/learning/explain",
            json={"knowledge_point": "partial application"},
        )

        items = db.query(NotebookItemModel).all()
        knowledge_ids = {i.knowledge_id for i in items}
        assert knowledge_ids == {"currying", "partial application"}

    def test_post_explain_validates_input(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/explain",
            json={"knowledge_point": ""},
        )

        assert resp.status_code == 422  # Pydantic validation error

    def test_health_endpoint(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
