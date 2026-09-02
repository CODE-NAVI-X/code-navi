"""API integration tests for Research Conversation Orchestrator endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.auth.dependencies import CurrentPrincipal, get_optional_principal
from code_navi.auth.rate_limiter import get_rate_limiter
from code_navi.db import Base, get_db
from code_navi.research.models import ResearchConversationModel
from code_navi.server import app


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    get_rate_limiter().reset()
    db_file = tmp_path / "test_api_orch.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.db_session_factory = TestingSession
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()
    get_rate_limiter().reset()


def _create_conversation(client: TestClient, **overrides: object) -> ResearchConversationModel:
    fields: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "profile_data": {},
        "messages_data": [],
        "owner_principal_id": None,
    }
    fields.update(overrides)
    conversation = ResearchConversationModel(**fields)
    with client.db_session_factory() as db:
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    return conversation


def test_orchestrator_state_and_direction_cards_api(client: TestClient) -> None:
    conv = _create_conversation(client, id="conv-api-1")

    # 1. Get initial state
    resp = client.get(f"/api/v1/research/conversations/{conv.id}/orchestrator/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == conv.id
    assert data["current_stage"] == "research_need"
    assert data["completed_stages"] == []

    # 2. Get direction cards (empty state initially when no learning context)
    resp = client.get(f"/api/v1/research/conversations/{conv.id}/orchestrator/direction-cards")
    assert resp.status_code == 200
    cards_data = resp.json()
    assert len(cards_data["cards"]) == 0


def test_orchestrator_learning_context_api(client: TestClient) -> None:
    conv = _create_conversation(client, id="conv-api-lc")

    # 1. Read empty learning context -> 200 with null fields
    resp = client.get(f"/api/v1/research/conversations/{conv.id}/orchestrator/learning-context")
    assert resp.status_code == 200
    data = resp.json()
    assert data["learned_content"] is None
    assert data["learning_progress"] is None

    # 2. Update learning context
    resp = client.put(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learning-context",
        json={"learned_content": "图注意力网络 GAT", "learning_progress": "已掌握多头注意力"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["learned_content"] == "图注意力网络 GAT"
    assert updated["learning_progress"] == "已掌握多头注意力"

    # 3. Dynamic direction cards now reflect GAT / Graph
    resp = client.get(f"/api/v1/research/conversations/{conv.id}/orchestrator/direction-cards")
    assert resp.status_code == 200
    cards = resp.json()["cards"]
    assert any("图" in c["title"] for c in cards)


def test_orchestrator_learner_profiles_api(client: TestClient) -> None:
    conv = _create_conversation(client, id="conv-api-prof")

    # 1. Initial read -> empty profile
    resp = client.get(f"/api/v1/research/conversations/{conv.id}/orchestrator/learner-profiles")
    assert resp.status_code == 200
    assert resp.json()["current_profile"] is None

    # 2. Update profile version 1
    resp = client.put(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learner-profiles",
        json={"hardware": "RTX 3080 10GB", "dev_experience": "精通 PyTorch"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_version"] == 1
    assert data["current_profile"]["hardware"] == "RTX 3080 10GB"
    assert len(data["history"]) == 1

    # 3. Update profile version 2
    resp = client.put(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learner-profiles",
        json={"weekly_hours": "12 小时/周", "grade": "研一"},
    )
    assert resp.status_code == 200
    data2 = resp.json()
    assert data2["current_version"] == 2
    assert data2["current_profile"]["hardware"] == "RTX 3080 10GB"
    assert data2["current_profile"]["weekly_hours"] == "12 小时/周"
    assert len(data2["history"]) == 2


def test_orchestrator_papers_api(client: TestClient) -> None:
    conv = _create_conversation(client, id="conv-api-paper")

    # 1. Select paper 1 with replace
    resp = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/papers/select",
        json={
            "paper_url": "https://arxiv.org/abs/1609.02907",
            "title": "GCN Paper",
            "purpose": "replace",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_paper"]["title"] == "GCN Paper"
    assert len(data["paper_history"]) == 1

    # 2. Select paper 2 with compare
    resp = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/papers/select",
        json={
            "paper_url": "https://arxiv.org/abs/1710.10903",
            "title": "GAT Paper",
            "purpose": "compare",
        },
    )
    assert resp.status_code == 200
    data2 = resp.json()
    assert data2["current_paper"]["title"] == "GCN Paper"
    assert len(data2["paper_history"]) == 2


def test_orchestrator_messages_flow_and_retry_api(client: TestClient) -> None:
    conv = _create_conversation(client, id="conv-api-msg")

    # 1. Send normal message
    resp = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
        json={"message": "我想研究图神经网络在引文网络上的节点分类"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["reply_message"]["sender"] == "assistant"
    assert data["state"]["current_stage"] == "research_need"

    # 2. Confirm to advance stage
    resp2 = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
        json={"message": "可以，就这样，我们继续！"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["state"]["current_stage"] == "research_plan"
    assert "research_need" in data2["state"]["completed_stages"]

    # 3. Retry when not in failed state returns 409
    retry_url = f"/api/v1/research/conversations/{conv.id}/orchestrator/messages/retry-last"
    retry_resp = client.post(retry_url)
    assert retry_resp.status_code == 409


def test_orchestrator_cross_owner_404_isolation(client: TestClient) -> None:
    conv = _create_conversation(
        client,
        id="conv-api-owner-a",
        owner_principal_id="principal-user-a",
    )

    # When user is user-B
    def override_user_b():
        return CurrentPrincipal(
            principal_id="principal-user-b",
            user_id="user-b",
            mode="authenticated",
            email_verified=True,
            session_id="sess-b",
        )

    app.dependency_overrides[get_optional_principal] = override_user_b
    try:
        resp = client.get(f"/api/v1/research/conversations/{conv.id}/orchestrator/state")
        assert resp.status_code == 404

        resp_msg = client.post(
            f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
            json={"message": "hello"},
        )
        assert resp_msg.status_code == 404
    finally:
        app.dependency_overrides.pop(get_optional_principal, None)
