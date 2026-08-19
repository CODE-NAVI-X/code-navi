"""Unit tests for the learning module (persistence, decontamination, API endpoints).

All tests use ``sqlite:///:memory:`` — no filesystem side-effects and fully
repeatable.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Force in-memory SQLite *before* any code_navi.learning imports execute.
os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.learning import services  # noqa: E402
from code_navi.learning.models import NotebookItemModel  # noqa: E402
from code_navi.learning.schemas import ExplainRequest  # noqa: E402
from code_navi.learning.services import (  # noqa: E402
    PromptDecontaminationEngine,
    QueryOrchestrator,
)
from code_navi.server import app  # noqa: E402
from kernel.adapters.jsonl_session import load_session  # noqa: E402
from kernel.providers.replay import first_structural_difference  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_event_logs(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep kernel Event JSONL out of the working tree during tests."""
    monkeypatch.setenv("CODE_NAVI_EVENTS_DIR", str(tmp_path_factory.mktemp("events")))


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep default learning tests offline even when a local .env has a key."""
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
            session_id="sess-a",
            knowledge_id="kn:recursion",
            item_type="note",
            content="Base case + inductive step.",
            extra_data={"source": "textbook"},
        )
        db.add(item)
        db.commit()

        fetched = db.query(NotebookItemModel).filter_by(knowledge_id="kn:recursion").first()
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
                    session_id="sess-a",
                    knowledge_id="k1",
                    item_type="summary",
                    content="Summary 1",
                ),
                NotebookItemModel(
                    user_id="u1",
                    session_id="sess-a",
                    knowledge_id="k2",
                    item_type="wrong_answer",
                    content="Answer 2",
                ),
            ]
        )
        db.commit()

        items = db.query(NotebookItemModel).filter_by(user_id="u1").all()
        assert len(items) == 2
        assert {i.item_type for i in items} == {"summary", "wrong_answer"}

    def test_extra_data_nullable(self, db: Session) -> None:
        item = NotebookItemModel(
            user_id="u1",
            session_id="sess-a",
            knowledge_id="k1",
            item_type="summary",
            content="No extra data.",
        )
        db.add(item)
        db.commit()

        fetched = db.query(NotebookItemModel).filter_by(knowledge_id="k1").first()
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

        assert "offline learning" in response.summary
        assert "[decontaminated]" not in response.summary
        assert response.citations[0].source_title == "Code Navi 离线演示说明"

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
        assert response.citations[0].source_title == "Code Navi 离线演示说明"

        # Verify notebook persistence
        item = db.query(NotebookItemModel).filter_by(knowledge_id="Dijkstra's algorithm").first()
        assert item is not None
        assert item.item_type == "summary"
        assert item.content == response.summary
        # The response exposes the archived id so the client can open the
        # learning → research context-transfer confirm flow for this record.
        assert response.notebook_item_id == item.id

    def test_explain_without_citations(self, db: Session) -> None:
        orchestrator = QueryOrchestrator()
        request = ExplainRequest(
            knowledge_point="hash table",
            include_citations=False,
        )

        response = orchestrator.explain(request, db)
        assert response.citations == []

    def test_offline_response_does_not_expose_internal_prompt(self, db: Session) -> None:
        orchestrator = QueryOrchestrator()
        request = ExplainRequest(knowledge_point="Big-O notation")

        response = orchestrator.explain(request, db)

        assert "Big-O notation" in response.summary
        assert "[decontaminated]" not in response.summary
        assert orchestrator.decontamination_engine.passphrase not in response.summary


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

    def test_workspace_context_requires_a_local_profile(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/explain",
            json={"knowledge_point": "Monad", "workspace_id": "workspace-without-profile"},
        )

        assert resp.status_code == 422

    def test_health_endpoint(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 5.  Kernel-routing invariants
# ---------------------------------------------------------------------------


class TestKernelRouting:
    """The learning module must reach models only through the kernel runtime."""

    def test_services_module_does_not_import_vendor_sdk(self) -> None:
        source = Path(services.__file__).read_text(encoding="utf-8")

        assert "from openai import" not in source
        assert "OpenAI(" not in source

    def test_explain_grants_no_tools(self) -> None:
        assert services.knowledge_explainer_agent.tool_names == ()

    def test_explain_writes_auditable_event_log(self, db: Session) -> None:
        response = QueryOrchestrator().explain(
            ExplainRequest(knowledge_point="binary search"),
            db,
        )

        item = db.query(NotebookItemModel).filter_by(knowledge_id="binary search").first()
        assert item is not None
        log_path = Path(item.extra_data["event_log_path"])
        assert log_path.is_file()

        events = load_session(log_path)
        event_types = [event.type for event in events]
        assert "run_started" in event_types
        assert "provider_called" in event_types
        assert "run_finished" in event_types
        assert response.summary

    def test_event_log_replays_identically(self, db: Session) -> None:
        QueryOrchestrator().explain(ExplainRequest(knowledge_point="quicksort"), db)

        item = db.query(NotebookItemModel).filter_by(knowledge_id="quicksort").first()
        assert item is not None
        events = load_session(Path(item.extra_data["event_log_path"]))

        # A recorded run must be replayable with no structural divergence.
        assert first_structural_difference(events, events) is None


# ---------------------------------------------------------------------------
# 6.  Notebook session scoping
# ---------------------------------------------------------------------------


class TestNotebookSessionScoping:
    """A notebook read must never leak another session's entries."""

    def test_notebook_only_returns_requested_session(self, client: TestClient) -> None:
        client.post(
            "/api/v1/learning/explain",
            json={"knowledge_point": "mine", "session_id": "sess-alice"},
        )
        client.post(
            "/api/v1/learning/explain",
            json={"knowledge_point": "theirs", "session_id": "sess-bob"},
        )

        alice = client.get("/api/v1/learning/notebook", params={"session_id": "sess-alice"})

        assert alice.status_code == 200
        body = alice.json()
        assert [item["session_id"] for item in body] == ["sess-alice"]
        assert {item["content"] for item in body} != set()
        bob_entries = [item for item in body if item["session_id"] == "sess-bob"]
        assert bob_entries == []

    def test_notebook_requires_session_id(self, client: TestClient) -> None:
        resp = client.get("/api/v1/learning/notebook")

        assert resp.status_code == 422

    def test_explain_echoes_session_id(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learning/explain",
            json={"knowledge_point": "echo", "session_id": "sess-echo"},
        )

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-echo"

    def test_explain_mints_session_id_when_omitted(self, client: TestClient) -> None:
        resp = client.post("/api/v1/learning/explain", json={"knowledge_point": "minted"})

        assert resp.status_code == 200
        minted = resp.json()["session_id"]
        assert minted.startswith("sess-")

        # The minted id must actually address the stored entry.
        items = client.get("/api/v1/learning/notebook", params={"session_id": minted}).json()
        assert [item["content"] for item in items] != []
