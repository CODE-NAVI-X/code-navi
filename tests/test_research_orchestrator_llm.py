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
    ResearchOrchestratorStateModel,
)
from code_navi.server import app


class FakeOrchestratorLlmGenerator:
    """Test fake for verifying prompt template assembly and LLM injection."""

    def __init__(
        self,
        responses: list[str | Exception | OrchestratorLlmOutcome] | None = None,
    ) -> None:
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
        if isinstance(resp, OrchestratorLlmOutcome):
            return resp
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


def test_unconfigured_provider_returns_failed_without_advancement(db_session) -> None:
    """P0: Unavailable/unconfigured provider returns failed without stage advancement."""
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=[OrchestratorLlmOutcome(status="unavailable", reason="Provider not configured")]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    conv = ResearchConversationModel(id="conv-llm-unavail", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-llm-unavail",
        SendOrchestratorMessageRequest(message="可以，确认这个需求，我们继续！"),
        db_session,
    )

    # Must return failed, NOT completed! No assistant success message, no stage advancement
    assert resp.status == "failed"
    assert resp.reply_message is None
    err_text = (resp.error or "").lower()
    assert "not configured" in err_text or "unavailable" in err_text
    assert resp.state.current_stage == "research_need"
    assert resp.state.last_status == "failed"
    assert resp.state.completed_stages == []


def test_empty_and_invalid_model_reply_returns_failed_without_advancement(db_session) -> None:
    """P0: Empty reply or output validation failure returns failed without advancing state."""
    # Turn 1: Empty reply
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=[
            OrchestratorLlmOutcome(status="generated", reply_text="   "),
            OrchestratorLlmOutcome(status="generated", reply_text="恭喜你，复现成功率达到 100%！"),
        ]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    conv = ResearchConversationModel(id="conv-llm-invalid", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Empty reply test
    resp1 = orchestrator.process_message(
        "conv-llm-invalid",
        SendOrchestratorMessageRequest(message="明确研究需求"),
        db_session,
    )
    assert resp1.status == "failed"
    assert resp1.reply_message is None
    assert resp1.state.current_stage == "research_need"
    assert resp1.state.last_status == "failed"

    # Validation failure test (forbidden percentage assertion)
    resp2 = orchestrator.process_message(
        "conv-llm-invalid",
        SendOrchestratorMessageRequest(message="可以，继续"),
        db_session,
    )
    assert resp2.status == "failed"
    assert resp2.reply_message is None
    assert resp2.state.current_stage == "research_need"
    assert resp2.state.last_status == "failed"


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


def test_retry_last_from_unavailable_updates_state_once(db_session) -> None:
    """P0: Retrying from unavailable/failed state updates state only once legally upon success."""
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=[
            OrchestratorLlmOutcome(status="unavailable", reason="Provider not configured"),
            "[Online Now] 姜姜上线啦！为你明确需求 (•̀ᴗ•́)و ̑̑",
        ]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    conv = ResearchConversationModel(id="conv-llm-retry-unavail", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Turn 1 fails due to unavailable
    resp1 = orchestrator.process_message(
        "conv-llm-retry-unavail",
        SendOrchestratorMessageRequest(message="我想研究图注意力网络"),
        db_session,
    )
    assert resp1.status == "failed"
    assert resp1.state.subtasks.need_defined is False

    # Retry succeeds -> exactly one update occurs
    resp2 = orchestrator.retry_last_message("conv-llm-retry-unavail", db_session)
    assert resp2.status == "completed"
    assert resp2.reply_message is not None
    assert "[Online Now]" in resp2.reply_message.content
    assert resp2.state.subtasks.need_defined is True

    # Assert conversation messages only has 1 user and 1 assistant message
    db_session.refresh(conv)
    assert len(conv.messages_data or []) == 2


def test_streaming_sse_endpoint_thinking_lifecycle(tmp_path) -> None:
    """P1: Valid LLM provider produces thinking -> completed sequence."""
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=["[Stream Reply] 姜姜为你梳理了思路 (•̀ᴗ•́)و ̑̑"]
    )
    test_orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    from code_navi.research import router as research_router
    orig_orch = research_router._conversation_orchestrator
    research_router._conversation_orchestrator = test_orchestrator

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
            resp = client.post(
                "/api/v1/research/conversations/conv-stream-1/orchestrator/messages/stream",
                json={"message": "我想研究图卷积网络在引文网络上的节点分类"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            text = resp.text

            assert "event: thinking" in text
            assert "event: completed" in text

            pos_thinking = text.find("event: thinking")
            pos_completed = text.find("event: completed")
            assert 0 <= pos_thinking < pos_completed
    finally:
        research_router._conversation_orchestrator = orig_orch
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


def test_streaming_sse_endpoint_unconfigured_provider_thinking_to_failed(tmp_path) -> None:
    """P0 & P1: When provider unavailable/failed, stream endpoint outputs thinking -> failed."""
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=[OrchestratorLlmOutcome(status="unavailable", reason="Provider not configured")]
    )
    test_orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    from code_navi.research import router as research_router
    orig_orch = research_router._conversation_orchestrator
    research_router._conversation_orchestrator = test_orchestrator

    db_file = tmp_path / "test_api_stream_fail.db"
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
            conv = ResearchConversationModel(
                id="conv-stream-fail", profile_data={}, messages_data=[]
            )
            db.add(conv)
            db.commit()

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/research/conversations/conv-stream-fail/orchestrator/messages/stream",
                json={"message": "继续"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            text = resp.text

            assert "event: thinking" in text
            assert "event: failed" in text
            assert "event: completed" not in text

            pos_thinking = text.find("event: thinking")
            pos_failed = text.find("event: failed")
            assert 0 <= pos_thinking < pos_failed
    finally:
        research_router._conversation_orchestrator = orig_orch
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


def test_sse_thinking_persisted_observable_state(tmp_path) -> None:
    """P1: In stream_message, last_status is persisted as 'thinking' in DB before yield."""
    fake_generator = FakeOrchestratorLlmGenerator(
        responses=["[Thinking Persisted Done] 回复完成 (＾▽＾)"]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_generator)

    db_file = tmp_path / "test_sse_persist.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    with TestingSession() as db:
        conv = ResearchConversationModel(id="conv-think-persist", profile_data={}, messages_data=[])
        db.add(conv)
        db.commit()

    with TestingSession() as db:
        gen = orchestrator.stream_message(
            "conv-think-persist",
            SendOrchestratorMessageRequest(message="我想研究图卷积"),
            db,
        )

        # 1. Consume the first event (thinking)
        first_event = next(gen)
        assert "event: thinking" in first_event

        # 2. In a separate DB session, verify state is persisted as 'thinking'
        with TestingSession() as db_check:
            state_row = db_check.get(ResearchOrchestratorStateModel, "conv-think-persist")
            assert state_row is not None
            assert state_row.last_status == "thinking"

        # 3. Consume the final event (completed)
        final_event = next(gen)
        assert "event: completed" in final_event

        # 4. In separate DB session, verify state transitioned to 'completed'
        with TestingSession() as db_check2:
            state_row2 = db_check2.get(ResearchOrchestratorStateModel, "conv-think-persist")
            assert state_row2 is not None
            assert state_row2.last_status == "completed"

    test_engine.dispose()
