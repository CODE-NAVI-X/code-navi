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


class FakeApiLlmGenerator:
    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
        from code_navi.research.conversation_orchestrator import OrchestratorLlmOutcome
        return OrchestratorLlmOutcome(
            status="generated",
            reply_text=f"姜姜已为你处理消息 (•̀ᴗ•́)و ̑̑：{user_prompt}",
        )


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

    from code_navi.research import router as research_router
    from code_navi.research.conversation_orchestrator import ResearchConversationOrchestrator
    orig_orch = research_router._conversation_orchestrator
    research_router._conversation_orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeApiLlmGenerator()
    )

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.db_session_factory = TestingSession
            yield test_client
    finally:
        research_router._conversation_orchestrator = orig_orch
        app.dependency_overrides.pop(get_db, None)
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


def test_send_orchestrator_message_rejects_extra_fields(client: TestClient) -> None:
    """Extra un-audited fields (e.g. provider_override, runtime_input) are rejected with 422."""
    conv = _create_conversation(client, id="conv-api-extra-fields")

    # 1. Reject provider_override
    resp1 = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
        json={
            "message": "我想研究图神经网络",
            "provider_override": "custom-deepseek",
        },
    )
    assert resp1.status_code == 422

    # 2. Reject runtime_input
    resp2 = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
        json={
            "message": "我想研究图神经网络",
            "runtime_input": "injected prompt text",
        },
    )
    assert resp2.status_code == 422

    # 3. Reject any arbitrary unknown field
    resp3 = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
        json={
            "message": "我想研究图神经网络",
            "unknown_injected_param": "foo",
        },
    )
    assert resp3.status_code == 422

    # 4. Valid message without extra fields succeeds with 200
    resp4 = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
        json={"message": "我想研究图神经网络"},
    )
    assert resp4.status_code == 200
    assert resp4.json()["status"] == "completed"


def test_orchestrator_stream_sse_endpoint_lifecycle_events(client: TestClient) -> None:
    """Verify stream SSE endpoint event names and ordering for completed and failed outcomes."""
    from code_navi.research import router as research_router
    from code_navi.research.conversation_orchestrator import (
        OrchestratorLlmOutcome,
        ResearchConversationOrchestrator,
    )

    conv_success = _create_conversation(client, id="conv-stream-success")
    conv_fail = _create_conversation(client, id="conv-stream-failure")

    # 1. Success lifecycle: thinking -> completed
    resp_success = client.post(
        f"/api/v1/research/conversations/{conv_success.id}/orchestrator/messages/stream",
        json={"message": "我想明确研究方向"},
    )
    assert resp_success.status_code == 200
    assert "text/event-stream" in resp_success.headers["content-type"]
    text_success = resp_success.text
    assert "event: thinking" in text_success
    assert "event: completed" in text_success
    assert "event: failed" not in text_success
    pos_thinking = text_success.find("event: thinking")
    pos_completed = text_success.find("event: completed")
    assert 0 <= pos_thinking < pos_completed

    # 2. Failure lifecycle: thinking -> failed
    class FailingGenerator:
        def generate(self, **kwargs):
            return OrchestratorLlmOutcome(
                status="failed",
                reason="DeepSeek remote service timeout",
            )

    orig_orch = research_router._conversation_orchestrator
    research_router._conversation_orchestrator = ResearchConversationOrchestrator(
        llm_generator=FailingGenerator()
    )
    try:
        resp_fail = client.post(
            f"/api/v1/research/conversations/{conv_fail.id}/orchestrator/messages/stream",
            json={"message": "我想明确研究方向"},
        )
        assert resp_fail.status_code == 200
        assert "text/event-stream" in resp_fail.headers["content-type"]
        text_fail = resp_fail.text
        assert "event: thinking" in text_fail
        assert "event: failed" in text_fail
        assert "event: completed" not in text_fail
        pos_thinking_fail = text_fail.find("event: thinking")
        pos_failed = text_fail.find("event: failed")
        assert 0 <= pos_thinking_fail < pos_failed
    finally:
        research_router._conversation_orchestrator = orig_orch


def test_retry_last_requires_failed_state_or_returns_409(client: TestClient) -> None:
    """POST retry-last requires previous turn to be failed, otherwise returns 409."""
    from code_navi.research import router as research_router
    from code_navi.research.conversation_orchestrator import (
        OrchestratorLlmOutcome,
        ResearchConversationOrchestrator,
    )

    conv = _create_conversation(client, id="conv-retry-lifecycle")
    retry_url = f"/api/v1/research/conversations/{conv.id}/orchestrator/messages/retry-last"

    # 1. Brand new state (no failed turns) -> 409
    resp1 = client.post(retry_url)
    assert resp1.status_code == 409

    # 2. Make a failed turn
    class FailingGenerator:
        def generate(self, **kwargs):
            return OrchestratorLlmOutcome(status="unavailable", reason="Provider down")

    orig_orch = research_router._conversation_orchestrator
    research_router._conversation_orchestrator = ResearchConversationOrchestrator(
        llm_generator=FailingGenerator()
    )
    try:
        fail_msg_resp = client.post(
            f"/api/v1/research/conversations/{conv.id}/orchestrator/messages",
            json={"message": "尝试确认这个需求，我们继续！"},
        )
        assert fail_msg_resp.status_code == 200
        assert fail_msg_resp.json()["status"] == "failed"
    finally:
        research_router._conversation_orchestrator = orig_orch

    # 3. Now previous turn is failed -> retry-last succeeds and returns 200 completed
    resp2 = client.post(retry_url)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "completed"
    assert data2["reply_message"] is not None

    # 4. Now state is completed -> next retry-last returns 409 again
    resp3 = client.post(retry_url)
    assert resp3.status_code == 409


def test_select_paper_rejects_extra_fields(client: TestClient) -> None:
    """SelectPaperRequest must reject unknown extra fields with 422 (extra='forbid')."""
    conv = _create_conversation(client, id="conv-api-paper-extra")
    resp = client.post(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/papers/select",
        json={
            "paper_url": "https://arxiv.org/abs/1710.10903",
            "title": "GAT Paper",
            "purpose": "replace",
            "extra_unauthorized_param": "forbidden_value",
        },
    )
    assert resp.status_code == 422


def test_learner_profile_update_rejects_extra_fields(client: TestClient) -> None:
    """LearnerProfileUpdateRequest must reject unknown extra fields with 422 (extra='forbid')."""
    conv = _create_conversation(client, id="conv-api-profile-extra")
    resp = client.put(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learner-profiles",
        json={
            "hardware": "RTX 4090 24GB",
            "weekly_hours": "15h",
            "injected_fake_field": "disallowed",
        },
    )
    assert resp.status_code == 422


def test_learning_context_input_rejects_extra_fields(client: TestClient) -> None:
    """LearningContextInput must reject unknown extra fields with 422 (extra='forbid')."""
    conv = _create_conversation(client, id="conv-api-learning-extra")
    resp = client.put(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learning-context",
        json={
            "learned_content": "图卷积网络基础",
            "learning_progress": "已完成第 3 节",
            "unexpected_property": "bad",
        },
    )
    assert resp.status_code == 422


def test_learning_context_progress_and_content_roundtrip_and_direction_cards(
    client: TestClient,
) -> None:
    """Learning context accepts progress/content, supports empty 200, and feeds direction cards."""
    conv = _create_conversation(client, id="conv-api-lc-roundtrip")

    # 1. Initial state: GET returns empty state (null fields) with HTTP 200 without fabricating data
    get_resp1 = client.get(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learning-context"
    )
    assert get_resp1.status_code == 200
    data1 = get_resp1.json()
    assert data1["learned_content"] is None
    assert data1["learning_progress"] is None

    # Empty direction cards
    cards_resp1 = client.get(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/direction-cards"
    )
    assert cards_resp1.status_code == 200
    assert cards_resp1.json()["cards"] == []

    # 2. PUT with both fields populated
    put_resp = client.put(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learning-context",
        json={
            "learned_content": "图神经网络与 GCN 消息传递机制",
            "learning_progress": "完成 80% 学习进度，已跑通基础练习",
        },
    )
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["learned_content"] == "图神经网络与 GCN 消息传递机制"
    assert put_data["learning_progress"] == "完成 80% 学习进度，已跑通基础练习"

    # 3. GET reflects both updated fields
    get_resp2 = client.get(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/learning-context"
    )
    assert get_resp2.status_code == 200
    data2 = get_resp2.json()
    assert data2["learned_content"] == "图神经网络与 GCN 消息传递机制"
    assert data2["learning_progress"] == "完成 80% 学习进度，已跑通基础练习"

    # 4. Direction cards read both fields and return dynamic recommendations
    cards_resp2 = client.get(
        f"/api/v1/research/conversations/{conv.id}/orchestrator/direction-cards"
    )
    assert cards_resp2.status_code == 200
    cards_data = cards_resp2.json()
    assert cards_data["learned_content"] == "图神经网络与 GCN 消息传递机制"
    assert cards_data["learning_progress"] == "完成 80% 学习进度，已跑通基础练习"
    assert len(cards_data["cards"]) > 0
