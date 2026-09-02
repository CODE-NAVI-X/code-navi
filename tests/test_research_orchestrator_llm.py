"""Tests for Research Conversation Orchestrator LLM integration,
failure recovery, and thinking lifecycle.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base, get_db
from code_navi.research.conversation_orchestrator import (
    OrchestratorLlmOutcome,
    ResearchConversationOrchestrator,
)
from code_navi.research.conversation_orchestrator_schemas import (
    SendOrchestratorMessageRequest,
)
from code_navi.research.models import (
    ResearchConversationModel,
)
from code_navi.server import app


class FakeOrchestratorLlmGenerator:
    """Test fake for verifying prompt template assembly and LLM injection."""

    def __init__(self, responses: list[str | Exception] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation_history: list[dict[str, object]] | tuple = (),
        conversation_id: str,
    ) -> OrchestratorLlmOutcome:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "conversation_history": list(conversation_history),
            "conversation_id": conversation_id,
        })
        if not self.responses:
            return OrchestratorLlmOutcome(
                status="generated",
                reply_text="[Fake LLM Reply] 这是来自 Fake Provider 的专业回复 (＾▽＾)。",
            )
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            return OrchestratorLlmOutcome(
                status="failed",
                reason=str(resp),
            )
        return OrchestratorLlmOutcome(
            status="generated",
            reply_text=resp,
        )


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_llm_orch.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()


def test_orchestrator_uses_fake_provider_output(db_session) -> None:
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=["[Provider Output] 姜姜为你梳理了研究需求：图卷积节点分类 (•̀ᴗ•́)و ̑̑"]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    conv = ResearchConversationModel(id="conv-llm-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-llm-1",
        SendOrchestratorMessageRequest(message="我想研究图卷积网络在引文网络上的节点分类"),
        db_session,
    )

    # 1. Output must come from provider, not hardcoded strings
    assert resp.status == "completed"
    assert resp.reply_message is not None
    assert "[Provider Output]" in resp.reply_message.content
    assert len(fake_generator.calls) == 1

    # 2. Fake provider received the prompt template with confirmed context
    call = fake_generator.calls[0]
    assert "姜姜" in str(call["system_prompt"])
    assert "图卷积网络在引文网络上的节点分类" in str(call["user_prompt"])


def test_provider_failure_sets_failed_state_without_changing_stage_or_subtasks(db_session) -> None:
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=[TimeoutError("DeepSeek API request timed out after 30s")]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    conv = ResearchConversationModel(id="conv-llm-fail", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Initial state
    state = orchestrator.get_or_create_state("conv-llm-fail", db_session)
    assert state.current_stage == "research_need"
    assert state.completed_stages == []

    # Send message that triggers provider failure
    resp = orchestrator.process_message(
        "conv-llm-fail",
        SendOrchestratorMessageRequest(message="我想做大模型量化剪枝"),
        db_session,
    )

    # Must be marked failed
    assert resp.status == "failed"
    assert "timed out" in (resp.error or "")
    assert resp.reply_message is None

    # State in DB must NOT have advanced stages or subtasks
    state_in_db = orchestrator.get_or_create_state("conv-llm-fail", db_session)
    assert state_in_db.current_stage == "research_need"
    assert state_in_db.completed_stages == []
    assert state_in_db.last_status == "failed"
    assert "timed out" in (state_in_db.last_error or "")

    # Profile versions must NOT have been changed
    profiles = orchestrator.get_learner_profiles("conv-llm-fail", db_session)
    assert len(profiles.history) == 0


def test_retry_last_message_after_provider_failure(db_session) -> None:
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=[
            TimeoutError("Connection dropped"),
            "[Provider Recovered] 重试成功！我们继续探讨大模型剪枝 (＾▽＾)。",
        ]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    conv = ResearchConversationModel(id="conv-llm-retry", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # 1. Turn 1 fails
    resp1 = orchestrator.process_message(
        "conv-llm-retry",
        SendOrchestratorMessageRequest(message="我想做大模型量化剪枝"),
        db_session,
    )
    assert resp1.status == "failed"

    # 2. Retry last message succeeds
    resp2 = orchestrator.retry_last_message("conv-llm-retry", db_session)
    assert resp2.status == "completed"
    assert resp2.reply_message is not None
    assert "[Provider Recovered]" in resp2.reply_message.content

    # State is now completed and has no last_error
    state_in_db = orchestrator.get_or_create_state("conv-llm-retry", db_session)
    assert state_in_db.last_status == "completed"
    assert state_in_db.last_error is None


def test_streaming_sse_endpoint_thinking_lifecycle(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    db_file = tmp_path / "test_api_stream.db"
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

    try:
        with TestingSession() as db:
            conv = ResearchConversationModel(id="conv-stream-1", profile_data={}, messages_data=[])
            db.add(conv)
            db.commit()

        with TestClient(app) as client:
            # Request stream endpoint
            resp = client.post(
                "/api/v1/research/conversations/conv-stream-1/orchestrator/messages/stream",
                json={"message": "我想研究图卷积网络在引文网络上的节点分类"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            text = resp.text

            # Must contain thinking event first, then completed event
            assert "event: thinking" in text
            assert "event: completed" in text

            # Thinking event must appear before completed event
            pos_thinking = text.find("event: thinking")
            pos_completed = text.find("event: completed")
            assert 0 <= pos_thinking < pos_completed
    finally:
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()

