"""Tests for Research Conversation Orchestrator LLM integration,
failure recovery, and thinking lifecycle.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from code_navi.db import Base, get_db
from code_navi.research.conversation_orchestrator import (
    OrchestratorLlmOutcome,
    ResearchConversationOrchestrator,
)
from code_navi.research.conversation_orchestrator_schemas import (
    LearningContextInput,
    SendOrchestratorMessageRequest,
)
from code_navi.research.conversation_prompt_templates import (
    RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION,
    RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME,
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


def test_all_eight_prompt_templates_dispatched_to_provider_via_process_message(
    db_session,
) -> None:
    """Verify that all 8 Prompt templates are dispatched to Provider via process_message()."""
    from code_navi.research.conversation_orchestrator_schemas import SelectPaperRequest

    # 1. Welcome and Bridge (fresh research_need session with opening intent)
    fake_gen_1 = FakeOrchestratorLlmGenerator()
    orch_1 = ResearchConversationOrchestrator(llm_generator=fake_gen_1)
    conv_1 = ResearchConversationModel(id="conv-tmpl-welcome", profile_data={}, messages_data=[])
    db_session.add(conv_1)
    db_session.commit()

    resp_1 = orch_1.process_message(
        "conv-tmpl-welcome",
        SendOrchestratorMessageRequest(message="你好，开始科研"),
        db_session,
    )
    assert resp_1.status == "completed"
    assert resp_1.state.current_stage == "research_need"
    assert resp_1.state.subtasks.need_defined is False
    assert len(fake_gen_1.calls) == 1
    call_1 = fake_gen_1.calls[0]
    assert (
        "欢迎同学并介绍研究方向" in call_1["system_prompt"]
        or "自然桥接" in call_1["system_prompt"]
        or "推荐研究方向" in call_1["user_prompt"]
    )

    # 2. Need Clarification (research topic entered in research_need stage)
    fake_gen_2 = FakeOrchestratorLlmGenerator()
    orch_2 = ResearchConversationOrchestrator(llm_generator=fake_gen_2)
    conv_2 = ResearchConversationModel(id="conv-tmpl-need", profile_data={}, messages_data=[])
    db_session.add(conv_2)
    db_session.commit()

    orch_2.process_message(
        "conv-tmpl-need",
        SendOrchestratorMessageRequest(message="我想研究图卷积网络在引文网络上的节点分类"),
        db_session,
    )
    assert len(fake_gen_2.calls) == 1
    call_2 = fake_gen_2.calls[0]
    assert "需求澄清" in call_2["system_prompt"]

    # 3. Profile and Plan (research_plan stage)
    fake_gen_3 = FakeOrchestratorLlmGenerator()
    orch_3 = ResearchConversationOrchestrator(llm_generator=fake_gen_3)
    conv_3 = ResearchConversationModel(id="conv-tmpl-plan", profile_data={}, messages_data=[])
    db_session.add(conv_3)
    db_session.commit()
    state_3 = ResearchOrchestratorStateModel(
        conversation_id="conv-tmpl-plan",
        current_stage="research_plan",
        completed_stages=["research_need"],
        subtasks={"need_defined": True, "profile_ready": False, "plan_generated": False},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_3)
    db_session.commit()

    orch_3.process_message(
        "conv-tmpl-plan",
        SendOrchestratorMessageRequest(message="我的硬件是 RTX 4090 24GB，每周可用 15 小时"),
        db_session,
    )
    assert len(fake_gen_3.calls) == 1
    call_3 = fake_gen_3.calls[0]
    assert (
        "学习者画像" in call_3["system_prompt"]
        or "【学生客观条件（画像）】" in call_3["user_prompt"]
    )

    # 4. Search Guidance (research_execution stage with search intent)
    fake_gen_4 = FakeOrchestratorLlmGenerator()
    orch_4 = ResearchConversationOrchestrator(llm_generator=fake_gen_4)
    conv_4 = ResearchConversationModel(id="conv-tmpl-search", profile_data={}, messages_data=[])
    db_session.add(conv_4)
    db_session.commit()
    state_4 = ResearchOrchestratorStateModel(
        conversation_id="conv-tmpl-search",
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={"need_defined": True, "profile_ready": True, "plan_generated": True},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_4)
    db_session.commit()

    orch_4.process_message(
        "conv-tmpl-search",
        SendOrchestratorMessageRequest(message="帮我检索图神经网络相关的核心论文关键词"),
        db_session,
    )
    assert len(fake_gen_4.calls) == 1
    call_4 = fake_gen_4.calls[0]
    assert "检索引导" in call_4["system_prompt"] or "【合规检索源】" in call_4["user_prompt"]
    assert "OpenAlex" in call_4["user_prompt"]
    assert "arXiv" in call_4["user_prompt"]

    # 5. Paper Intro (research_execution stage with selected current paper)
    fake_gen_5 = FakeOrchestratorLlmGenerator()
    orch_5 = ResearchConversationOrchestrator(llm_generator=fake_gen_5)
    conv_5 = ResearchConversationModel(id="conv-tmpl-paper", profile_data={}, messages_data=[])
    db_session.add(conv_5)
    db_session.commit()
    state_5 = ResearchOrchestratorStateModel(
        conversation_id="conv-tmpl-paper",
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={
            "need_defined": True,
            "profile_ready": True,
            "plan_generated": True,
            "paper_selected": True,
        },
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_5)
    db_session.commit()
    orch_5.select_paper(
        "conv-tmpl-paper",
        SelectPaperRequest(
            paper_url="https://arxiv.org/abs/1609.02907",
            title="Semi-Supervised Classification with Graph Convolutional Networks",
            purpose="replace",
        ),
        db_session,
    )

    orch_5.process_message(
        "conv-tmpl-paper",
        SendOrchestratorMessageRequest(message="请详细介绍一下这篇选定的 GCN 论文核心内容"),
        db_session,
    )
    assert len(fake_gen_5.calls) == 1
    call_5 = fake_gen_5.calls[0]
    assert (
        "论文介绍" in call_5["system_prompt"]
        or "精读" in call_5["system_prompt"]
        or "【选定论文核心信息】" in call_5["user_prompt"]
    )

    # 6. Experiment Design (research_execution stage without paper)
    fake_gen_6 = FakeOrchestratorLlmGenerator()
    orch_6 = ResearchConversationOrchestrator(llm_generator=fake_gen_6)
    conv_6 = ResearchConversationModel(id="conv-tmpl-exp", profile_data={}, messages_data=[])
    db_session.add(conv_6)
    db_session.commit()
    state_6 = ResearchOrchestratorStateModel(
        conversation_id="conv-tmpl-exp",
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={"need_defined": True, "profile_ready": True, "plan_generated": True},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_6)
    db_session.commit()

    orch_6.process_message(
        "conv-tmpl-exp",
        SendOrchestratorMessageRequest(message="请针对当前的图节点分类任务，推荐标准的训练流程和评测指标"),
        db_session,
    )
    assert len(fake_gen_6.calls) == 1
    call_6 = fake_gen_6.calls[0]
    assert (
        "白名单标准评估指标" in call_6["user_prompt"]
        or "to_verify" in call_6["system_prompt"]
    )

    # 7. Result Analysis (research_analysis stage)
    fake_gen_7 = FakeOrchestratorLlmGenerator()
    orch_7 = ResearchConversationOrchestrator(llm_generator=fake_gen_7)
    conv_7 = ResearchConversationModel(id="conv-tmpl-result", profile_data={}, messages_data=[])
    db_session.add(conv_7)
    db_session.commit()
    state_7 = ResearchOrchestratorStateModel(
        conversation_id="conv-tmpl-result",
        current_stage="research_analysis",
        completed_stages=["research_need", "research_plan", "research_execution"],
        subtasks={
            "need_defined": True,
            "profile_ready": True,
            "plan_generated": True,
            "paper_selected": True,
            "experiment_designed": True,
            "results_analyzed": False,
        },
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_7)
    db_session.commit()

    orch_7.process_message(
        "conv-tmpl-result",
        SendOrchestratorMessageRequest(
            message=(
                "在 Cora 测试集使用 GCN，lr=0.01、seed=42、训练 200 epoch；"
                "Accuracy=83.5%，Loss=0.24，相比 baseline 79.2% 提升 4.3 个百分点。"
            )
        ),
        db_session,
    )
    assert len(fake_gen_7.calls) == 1
    call_7 = fake_gen_7.calls[0]
    assert (
        "结果分析" in call_7["system_prompt"]
        or "【用户最新实验结果与现象】" in call_7["user_prompt"]
    )

    # 8. Stage Transition (confirmed subtasks advancing to next stage)
    fake_gen_8 = FakeOrchestratorLlmGenerator()
    orch_8 = ResearchConversationOrchestrator(llm_generator=fake_gen_8)
    conv_8 = ResearchConversationModel(id="conv-tmpl-transition", profile_data={}, messages_data=[])
    db_session.add(conv_8)
    db_session.commit()
    state_8 = ResearchOrchestratorStateModel(
        conversation_id="conv-tmpl-transition",
        current_stage="research_need",
        completed_stages=[],
        subtasks={"need_defined": True, "profile_ready": False, "plan_generated": False},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_8)
    db_session.commit()

    orch_8.process_message(
        "conv-tmpl-transition",
        SendOrchestratorMessageRequest(message="可以，确认这个需求，我们继续！"),
        db_session,
    )
    assert len(fake_gen_8.calls) == 1
    call_8 = fake_gen_8.calls[0]
    assert "阶段切换" in call_8["system_prompt"] or "【阶段跃迁】" in call_8["user_prompt"]


def test_opening_greeting_vs_concrete_topic_in_research_need_stage(db_session) -> None:
    """Regression test for opening greeting intent vs concrete topic in research_need stage."""
    fake_gen = FakeOrchestratorLlmGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_gen)

    # 1. Pure opening greeting ("你好，开始科研") -> welcome template, need_defined=False
    conv_1 = ResearchConversationModel(id="conv-open-1", profile_data={}, messages_data=[])
    db_session.add(conv_1)
    db_session.commit()

    resp_1 = orchestrator.process_message(
        "conv-open-1",
        SendOrchestratorMessageRequest(message="你好，开始科研"),
        db_session,
    )
    assert resp_1.status == "completed"
    assert resp_1.state.current_stage == "research_need"
    assert resp_1.state.subtasks.need_defined is False
    assert len(fake_gen.calls) == 1
    call_1 = fake_gen.calls[0]
    assert (
        "欢迎同学并介绍研究方向" in call_1["system_prompt"]
        or "推荐研究方向" in call_1["user_prompt"]
    )

    # 2. Greeting with concrete topic ("你好，我想研究图卷积网络节点分类") -> need_clarification
    fake_gen.calls.clear()
    conv_2 = ResearchConversationModel(id="conv-open-2", profile_data={}, messages_data=[])
    db_session.add(conv_2)
    db_session.commit()

    resp_2 = orchestrator.process_message(
        "conv-open-2",
        SendOrchestratorMessageRequest(message="你好，我想研究图卷积网络节点分类"),
        db_session,
    )
    assert resp_2.status == "completed"
    assert resp_2.state.current_stage == "research_need"
    assert len(fake_gen.calls) == 1
    call_2 = fake_gen.calls[0]
    assert "需求澄清" in call_2["system_prompt"]
    assert "欢迎同学并介绍研究方向" not in call_2["system_prompt"]
    assert "【基于学习内容动态生成的推荐研究方向】" not in call_2["user_prompt"]


def test_orchestrator_allows_compliant_reproduction_negation_and_rejects_affirmative_claim(
    db_session,
) -> None:
    """C. Orchestrator: allow compliant negations, reject ungrounded reproduction claims."""
    # 1. Compliant negation from Provider -> status completed
    fake_gen_ok = FakeOrchestratorLlmGenerator(
        responses=[
            "目前还不能下“复现成功”的结论，仍需核验数据划分、训练动态与论文基线 (•̀ᴗ•́)و ̑̑。"
        ]
    )
    orchestrator_ok = ResearchConversationOrchestrator(llm_generator=fake_gen_ok)
    conv_ok = ResearchConversationModel(id="conv-repro-ok", profile_data={}, messages_data=[])
    db_session.add(conv_ok)
    db_session.commit()

    resp_ok = orchestrator_ok.process_message(
        "conv-repro-ok",
        SendOrchestratorMessageRequest(message="在 Cora 上测得 Accuracy 80.8%"),
        db_session,
    )
    assert resp_ok.status == "completed"
    assert resp_ok.reply_message is not None
    assert "目前还不能下“复现成功”的结论" in resp_ok.reply_message.content

    # 2. Affirmative claim "视为复现成功" from Provider -> status failed
    fake_gen_bad1 = FakeOrchestratorLlmGenerator(
        responses=[
            "若 Accuracy 落在 80.0% - 82.5%，即可视为复现成功 (•̀ᴗ•́)و ̑̑。"
        ]
    )
    orchestrator_bad1 = ResearchConversationOrchestrator(llm_generator=fake_gen_bad1)
    conv_bad1 = ResearchConversationModel(id="conv-repro-bad1", profile_data={}, messages_data=[])
    db_session.add(conv_bad1)
    db_session.commit()

    resp_bad1 = orchestrator_bad1.process_message(
        "conv-repro-bad1",
        SendOrchestratorMessageRequest(message="我们来设计实验评估标准"),
        db_session,
    )
    assert resp_bad1.status == "failed"
    assert resp_bad1.reply_message is None
    assert resp_bad1.state.last_status == "failed"
    assert "validation failure" in resp_bad1.error

    # 3. Affirmative claim "本次实验已复现成功" -> status failed
    fake_gen_bad2 = FakeOrchestratorLlmGenerator(
        responses=[
            "本次实验已复现成功 (•̀ᴗ•́)و ̑̑！"
        ]
    )
    orchestrator_bad2 = ResearchConversationOrchestrator(llm_generator=fake_gen_bad2)
    conv_bad2 = ResearchConversationModel(id="conv-repro-bad2", profile_data={}, messages_data=[])
    db_session.add(conv_bad2)
    db_session.commit()

    resp_bad2 = orchestrator_bad2.process_message(
        "conv-repro-bad2",
        SendOrchestratorMessageRequest(message="结果出来了"),
        db_session,
    )
    assert resp_bad2.status == "failed"
    assert resp_bad2.reply_message is None
    assert resp_bad2.state.last_status == "failed"

    # 4. Mixed clause: negation in first half + positive claim in second half -> failed
    fake_gen_mixed = FakeOrchestratorLlmGenerator(
        responses=[
            "尚未确认复现成功，但本次实验已复现成功 (•̀ᴗ•́)و ̑̑！"
        ]
    )
    orchestrator_mixed = ResearchConversationOrchestrator(llm_generator=fake_gen_mixed)
    conv_mixed = ResearchConversationModel(id="conv-repro-mixed", profile_data={}, messages_data=[])
    db_session.add(conv_mixed)
    db_session.commit()

    resp_mixed = orchestrator_mixed.process_message(
        "conv-repro-mixed",
        SendOrchestratorMessageRequest(message="看一下整体状态"),
        db_session,
    )
    assert resp_mixed.status == "failed"
    assert resp_mixed.reply_message is None
    assert resp_mixed.state.last_status == "failed"

    # 5. Semantic violation: "本次已成功复现 GCN。" -> failed, no state advance
    fake_gen_v1 = FakeOrchestratorLlmGenerator(
        responses=["本次已成功复现 GCN (•̀ᴗ•́)و ̑̑！"]
    )
    orchestrator_v1 = ResearchConversationOrchestrator(llm_generator=fake_gen_v1)
    conv_v1 = ResearchConversationModel(id="conv-repro-v1", profile_data={}, messages_data=[])
    db_session.add(conv_v1)
    db_session.commit()

    resp_v1 = orchestrator_v1.process_message(
        "conv-repro-v1",
        SendOrchestratorMessageRequest(message="看一下结果"),
        db_session,
    )
    assert resp_v1.status == "failed"
    assert resp_v1.reply_message is None
    assert resp_v1.state.last_status == "failed"
    assert resp_v1.state.current_stage == "research_need"
    assert resp_v1.state.subtasks.need_defined is False

    # 6. Semantic violation: "Accuracy 超过 81% 即算复现通过。" -> failed
    fake_gen_v2 = FakeOrchestratorLlmGenerator(
        responses=["Accuracy 超过 81% 即算复现通过 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_v2 = ResearchConversationOrchestrator(llm_generator=fake_gen_v2)
    conv_v2 = ResearchConversationModel(id="conv-repro-v2", profile_data={}, messages_data=[])
    db_session.add(conv_v2)
    db_session.commit()

    resp_v2 = orchestrator_v2.process_message(
        "conv-repro-v2",
        SendOrchestratorMessageRequest(message="设计评估指标"),
        db_session,
    )
    assert resp_v2.status == "failed"
    assert resp_v2.reply_message is None
    assert resp_v2.state.last_status == "failed"

    # 7. Safe boundary case: "复现成功不代表论文结论正确，仍需人工核验。" -> completed
    fake_gen_safe = FakeOrchestratorLlmGenerator(
        responses=["复现成功不代表论文结论正确，仍需人工核验 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_safe = ResearchConversationOrchestrator(llm_generator=fake_gen_safe)
    conv_safe = ResearchConversationModel(id="conv-repro-safe", profile_data={}, messages_data=[])
    db_session.add(conv_safe)
    db_session.commit()

    resp_safe = orchestrator_safe.process_message(
        "conv-repro-safe",
        SendOrchestratorMessageRequest(message="指标核验进展"),
        db_session,
    )
    assert resp_safe.status == "completed"
    assert resp_safe.reply_message is not None
    assert "复现成功不代表论文结论正确" in resp_safe.reply_message.content

    # 8. Unrelated negation in first half + positive claim in second half -> failed
    fake_gen_v3 = FakeOrchestratorLlmGenerator(
        responses=["实验不稳定且已复现成功 (•̀ᴗ•́)و ̑̑！"]
    )
    orchestrator_v3 = ResearchConversationOrchestrator(llm_generator=fake_gen_v3)
    conv_v3 = ResearchConversationModel(id="conv-repro-v3", profile_data={}, messages_data=[])
    db_session.add(conv_v3)
    db_session.commit()

    resp_v3 = orchestrator_v3.process_message(
        "conv-repro-v3",
        SendOrchestratorMessageRequest(message="评估实验状态"),
        db_session,
    )
    assert resp_v3.status == "failed"
    assert resp_v3.reply_message is None
    assert resp_v3.state.last_status == "failed"
    assert resp_v3.state.current_stage == "research_need"
    assert resp_v3.state.subtasks.need_defined is False

    # 9. Extended reproduction term "模型已稳定重现论文结果。" -> failed
    fake_gen_v4 = FakeOrchestratorLlmGenerator(
        responses=["模型已稳定重现论文结果 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_v4 = ResearchConversationOrchestrator(llm_generator=fake_gen_v4)
    conv_v4 = ResearchConversationModel(id="conv-repro-v4", profile_data={}, messages_data=[])
    db_session.add(conv_v4)
    db_session.commit()

    resp_v4 = orchestrator_v4.process_message(
        "conv-repro-v4",
        SendOrchestratorMessageRequest(message="看一下重现情况"),
        db_session,
    )
    assert resp_v4.status == "failed"
    assert resp_v4.reply_message is None
    assert resp_v4.state.last_status == "failed"
    assert resp_v4.state.current_stage == "research_need"
    assert resp_v4.state.subtasks.need_defined is False

    # 10. Positive reproduction synonym: "模型已经复现论文结果。" -> failed
    fake_gen_v5 = FakeOrchestratorLlmGenerator(
        responses=["模型已经复现论文结果 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_v5 = ResearchConversationOrchestrator(llm_generator=fake_gen_v5)
    conv_v5 = ResearchConversationModel(id="conv-repro-v5", profile_data={}, messages_data=[])
    db_session.add(conv_v5)
    db_session.commit()

    resp_v5 = orchestrator_v5.process_message(
        "conv-repro-v5",
        SendOrchestratorMessageRequest(message="检查论文复现状态"),
        db_session,
    )
    assert resp_v5.status == "failed"
    assert resp_v5.reply_message is None
    assert resp_v5.state.last_status == "failed"
    assert resp_v5.state.current_stage == "research_need"
    assert resp_v5.state.subtasks.need_defined is False

    # 11. Contextual risk reminder: "严禁声称复现成功率，当前结果仍待核验。" -> completed
    fake_gen_safe2 = FakeOrchestratorLlmGenerator(
        responses=["严禁声称复现成功率，当前结果仍待核验 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_safe2 = ResearchConversationOrchestrator(llm_generator=fake_gen_safe2)
    conv_safe2 = ResearchConversationModel(id="conv-repro-safe2", profile_data={}, messages_data=[])
    db_session.add(conv_safe2)
    db_session.commit()

    resp_safe2 = orchestrator_safe2.process_message(
        "conv-repro-safe2",
        SendOrchestratorMessageRequest(message="成功率如何评估"),
        db_session,
    )
    assert resp_safe2.status == "completed"
    assert resp_safe2.reply_message is not None
    assert "严禁声称复现成功率" in resp_safe2.reply_message.content

    # 12. Final R4 positive claim "模型成功跑通了论文复现实验。" -> failed
    fake_gen_v6 = FakeOrchestratorLlmGenerator(
        responses=["模型成功跑通了论文复现实验 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_v6 = ResearchConversationOrchestrator(llm_generator=fake_gen_v6)
    conv_v6 = ResearchConversationModel(id="conv-repro-v6", profile_data={}, messages_data=[])
    db_session.add(conv_v6)
    db_session.commit()

    resp_v6 = orchestrator_v6.process_message(
        "conv-repro-v6",
        SendOrchestratorMessageRequest(message="检查实验运行结果"),
        db_session,
    )
    assert resp_v6.status == "failed"
    assert resp_v6.reply_message is None
    assert resp_v6.state.last_status == "failed"
    assert resp_v6.state.current_stage == "research_need"
    assert resp_v6.state.subtasks.need_defined is False

    # 13. Evidence boundary violation "指标达到 81%，说明复现结果与论文一致。" -> failed
    fake_gen_v7 = FakeOrchestratorLlmGenerator(
        responses=["指标达到 81%，说明复现结果与论文一致 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_v7 = ResearchConversationOrchestrator(llm_generator=fake_gen_v7)
    conv_v7 = ResearchConversationModel(id="conv-repro-v7", profile_data={}, messages_data=[])
    db_session.add(conv_v7)
    db_session.commit()

    resp_v7 = orchestrator_v7.process_message(
        "conv-repro-v7",
        SendOrchestratorMessageRequest(message="对比指标"),
        db_session,
    )
    assert resp_v7.status == "failed"
    assert resp_v7.reply_message is None
    assert resp_v7.state.last_status == "failed"
    assert resp_v7.state.current_stage == "research_need"
    assert resp_v7.state.subtasks.need_defined is False

    # 14. Evidence boundary safe case "实验完成率的计算口径仍待确认。" -> completed
    fake_gen_safe3 = FakeOrchestratorLlmGenerator(
        responses=["实验完成率的计算口径仍待确认 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_safe3 = ResearchConversationOrchestrator(llm_generator=fake_gen_safe3)
    conv_safe3 = ResearchConversationModel(id="conv-repro-safe3", profile_data={}, messages_data=[])
    db_session.add(conv_safe3)
    db_session.commit()

    resp_safe3 = orchestrator_safe3.process_message(
        "conv-repro-safe3",
        SendOrchestratorMessageRequest(message="口径确认"),
        db_session,
    )
    assert resp_safe3.status == "completed"
    assert resp_safe3.reply_message is not None
    assert "实验完成率的计算口径仍待确认" in resp_safe3.reply_message.content

    # 15. P1-A violation "结果和原论文吻合，可以进入下一阶段。" -> failed
    fake_gen_v8 = FakeOrchestratorLlmGenerator(
        responses=["结果和原论文吻合，可以进入下一阶段 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_v8 = ResearchConversationOrchestrator(llm_generator=fake_gen_v8)
    conv_v8 = ResearchConversationModel(id="conv-repro-v8", profile_data={}, messages_data=[])
    db_session.add(conv_v8)
    db_session.commit()

    resp_v8 = orchestrator_v8.process_message(
        "conv-repro-v8",
        SendOrchestratorMessageRequest(message="检查吻合度"),
        db_session,
    )
    assert resp_v8.status == "failed"
    assert resp_v8.reply_message is None
    assert resp_v8.state.last_status == "failed"
    assert resp_v8.state.current_stage == "research_need"
    assert resp_v8.state.subtasks.need_defined is False

    # 16. P1-B intra-clause safe case "实验完成率作为实验过程指标，而非复现结论。" -> completed
    fake_gen_safe4 = FakeOrchestratorLlmGenerator(
        responses=["实验完成率作为实验过程指标，而非复现结论 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_safe4 = ResearchConversationOrchestrator(llm_generator=fake_gen_safe4)
    conv_safe4 = ResearchConversationModel(id="conv-repro-safe4", profile_data={}, messages_data=[])
    db_session.add(conv_safe4)
    db_session.commit()

    resp_safe4 = orchestrator_safe4.process_message(
        "conv-repro-safe4",
        SendOrchestratorMessageRequest(message="过程指标说明"),
        db_session,
    )
    assert resp_safe4.status == "completed"
    assert resp_safe4.reply_message is not None
    assert "实验完成率作为实验过程指标" in resp_safe4.reply_message.content

    # 17. Consistency violation "指标达到81%，复现指标与论文一致。" -> failed
    fake_gen_v9 = FakeOrchestratorLlmGenerator(
        responses=["指标达到81%，复现指标与论文一致 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_v9 = ResearchConversationOrchestrator(llm_generator=fake_gen_v9)
    conv_v9 = ResearchConversationModel(id="conv-repro-v9", profile_data={}, messages_data=[])
    db_session.add(conv_v9)
    db_session.commit()

    resp_v9 = orchestrator_v9.process_message(
        "conv-repro-v9",
        SendOrchestratorMessageRequest(message="检查指标一致性"),
        db_session,
    )
    assert resp_v9.status == "failed"
    assert resp_v9.reply_message is None
    assert resp_v9.state.last_status == "failed"
    assert resp_v9.state.current_stage == "research_need"
    assert resp_v9.state.subtasks.need_defined is False

    # 18. Compound coordination safe case "不应断言复现成功或复现实验完成。" -> completed
    fake_gen_safe5 = FakeOrchestratorLlmGenerator(
        responses=["不应断言复现成功或复现实验完成 (•̀ᴗ•́)و ̑̑。"]
    )
    orchestrator_safe5 = ResearchConversationOrchestrator(llm_generator=fake_gen_safe5)
    conv_safe5 = ResearchConversationModel(id="conv-repro-safe5", profile_data={}, messages_data=[])
    db_session.add(conv_safe5)
    db_session.commit()

    resp_safe5 = orchestrator_safe5.process_message(
        "conv-repro-safe5",
        SendOrchestratorMessageRequest(message="复合边界说明"),
        db_session,
    )
    assert resp_safe5.status == "completed"
    assert resp_safe5.reply_message is not None
    assert "不应断言复现成功或复现实验完成" in resp_safe5.reply_message.content


def test_orchestrator_p1_reproduction_boundary_regressions(db_session) -> None:
    """P1 Orchestrator regressions:
    1. Provider affirmative completion violation -> failed, no advancement.
    2. Provider compliant fact/to_verify and conditional boundary -> completed.
    """
    # 1. Provider outputs word-order variant completion claim -> status failed
    fake_gen_bad = FakeOrchestratorLlmGenerator(
        responses=["本轮实验已通过复现验证 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_bad = ResearchConversationOrchestrator(llm_generator=fake_gen_bad)
    conv_bad = ResearchConversationModel(id="conv-p1-bad", profile_data={}, messages_data=[])
    db_session.add(conv_bad)
    db_session.commit()

    resp_bad = orch_bad.process_message(
        "conv-p1-bad",
        SendOrchestratorMessageRequest(message="验证实验完成情况"),
        db_session,
    )
    assert resp_bad.status == "failed"
    assert resp_bad.reply_message is None
    assert resp_bad.state.last_status == "failed"
    assert "Jiang Jiang output boundary validation failure" in (resp_bad.error or "")
    assert resp_bad.state.current_stage == "research_need"
    assert resp_bad.state.subtasks.need_defined is False
    state_in_db = orch_bad.get_state_model("conv-p1-bad", db_session)
    assert state_in_db.current_plan is None
    assert len(state_in_db.plan_history or []) == 0
    profiles_bad = orch_bad.get_learner_profiles("conv-p1-bad", db_session)
    assert len(profiles_bad.history) == 0

    # 2. Unsubstantiated user report without source -> status failed, no advancement
    fake_gen_unproven = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告实验结果与论文一致；to_verify：仍需核验 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_unproven = ResearchConversationOrchestrator(llm_generator=fake_gen_unproven)
    conv_unproven = ResearchConversationModel(
        id="conv-p1-unproven", profile_data={}, messages_data=[]
    )
    db_session.add(conv_unproven)
    db_session.commit()

    resp_unproven = orch_unproven.process_message(
        "conv-p1-unproven",
        SendOrchestratorMessageRequest(message="汇报当前事实边界"),
        db_session,
    )
    assert resp_unproven.status == "failed"
    assert resp_unproven.reply_message is None
    assert resp_unproven.state.last_status == "failed"
    assert "Jiang Jiang output boundary validation failure" in (resp_unproven.error or "")
    assert resp_unproven.state.current_stage == "research_need"
    assert resp_unproven.state.subtasks.need_defined is False
    state_in_db2 = orch_unproven.get_state_model("conv-p1-unproven", db_session)
    assert state_in_db2.current_plan is None
    assert len(state_in_db2.plan_history or []) == 0
    profiles_unproven = orch_unproven.get_learner_profiles("conv-p1-unproven", db_session)
    assert len(profiles_unproven.history) == 0

    # 3. Irrelevant to_verify without source -> status failed
    fake_gen_irrelevant = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告实验结果与论文一致；to_verify：确认显存容量 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_irrelevant = ResearchConversationOrchestrator(llm_generator=fake_gen_irrelevant)
    conv_irrelevant = ResearchConversationModel(
        id="conv-p1-irrel", profile_data={}, messages_data=[]
    )
    db_session.add(conv_irrelevant)
    db_session.commit()

    resp_irrelevant = orch_irrelevant.process_message(
        "conv-p1-irrel",
        SendOrchestratorMessageRequest(message="汇报当前事实边界"),
        db_session,
    )
    assert resp_irrelevant.status == "failed"
    assert resp_irrelevant.reply_message is None

    # 4. User provides authentic fact in current message -> status completed
    fake_gen_proven = FakeOrchestratorLlmGenerator(
        responses=[
            "fact：用户报告实验结果与论文一致；\n"
            "to_verify：仍需核验数据划分、随机种子和指标计算口径 (•̀ᴗ•́)و ̑̑。"
        ]
    )
    orch_proven = ResearchConversationOrchestrator(llm_generator=fake_gen_proven)
    conv_proven = ResearchConversationModel(
        id="conv-p1-proven", profile_data={}, messages_data=[]
    )
    db_session.add(conv_proven)
    db_session.commit()

    resp_proven = orch_proven.process_message(
        "conv-p1-proven",
        SendOrchestratorMessageRequest(
            message="我观察到本次实验结果与论文结果一致，但还没有完成核验。"
        ),
        db_session,
    )
    assert resp_proven.status == "completed"
    assert resp_proven.reply_message is not None
    assert "fact：用户报告实验结果与论文一致" in resp_proven.reply_message.content

    # 5. Persisted historical evidence enables subsequent compliant restatement
    fake_gen_hist = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告实验结果与论文一致；to_verify：仍需核验数据划分 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_hist = ResearchConversationOrchestrator(llm_generator=fake_gen_hist)
    conv_hist = ResearchConversationModel(
        id="conv-p1-hist",
        profile_data={},
        messages_data=[
            {
                "sender": "user",
                "role": "user",
                "content": "我观察到本次实验结果与论文结果一致，但还没有完成核验。",
            }
        ],
    )
    db_session.add(conv_hist)
    db_session.commit()

    resp_hist = orch_hist.process_message(
        "conv-p1-hist",
        SendOrchestratorMessageRequest(message="汇报当前事实边界"),
        db_session,
    )
    assert resp_hist.status == "completed"
    assert resp_hist.reply_message is not None
    assert "fact：用户报告实验结果与论文一致" in resp_hist.reply_message.content

    # 6. User provides fact, but model claims ungrounded affirmative completion -> status failed
    fake_gen_cross = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告实验结果与论文一致；但姜姜确认已经复现成功 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_cross = ResearchConversationOrchestrator(llm_generator=fake_gen_cross)
    conv_cross = ResearchConversationModel(
        id="conv-p1-cross", profile_data={}, messages_data=[]
    )
    db_session.add(conv_cross)
    db_session.commit()

    resp_cross = orch_cross.process_message(
        "conv-p1-cross",
        SendOrchestratorMessageRequest(
            message="我观察到本次实验结果与论文结果一致，但还没有完成核验。"
        ),
        db_session,
    )
    assert resp_cross.status == "failed"
    assert resp_cross.reply_message is None

    # 7. Provider outputs compliant conditional boundary -> status completed
    fake_gen_ok2 = FakeOrchestratorLlmGenerator(
        responses=["即使实验结果与论文一致，也不能据此认定复现成功 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_ok2 = ResearchConversationOrchestrator(llm_generator=fake_gen_ok2)
    conv_ok2 = ResearchConversationModel(id="conv-p1-ok2", profile_data={}, messages_data=[])
    db_session.add(conv_ok2)
    db_session.commit()

    resp_ok2 = orch_ok2.process_message(
        "conv-p1-ok2",
        SendOrchestratorMessageRequest(message="说明基线一致与复现成功的边界"),
        db_session,
    )
    assert resp_ok2.status == "completed"
    assert resp_ok2.reply_message is not None
    assert "即使实验结果与论文一致，也不能据此认定复现成功" in resp_ok2.reply_message.content

    # 8. Category mismatch between user evidence and model claim -> status failed
    fake_gen_mismatch = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告指标达到论文基线；to_verify：仍需核验 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_mismatch = ResearchConversationOrchestrator(llm_generator=fake_gen_mismatch)
    conv_mismatch = ResearchConversationModel(
        id="conv-p1-mismatch", profile_data={}, messages_data=[]
    )
    db_session.add(conv_mismatch)
    db_session.commit()

    resp_mismatch = orch_mismatch.process_message(
        "conv-p1-mismatch",
        SendOrchestratorMessageRequest(
            message="我观察到本次实验结果与论文结果一致，但还没有完成核验。"
        ),
        db_session,
    )
    assert resp_mismatch.status == "failed"
    assert resp_mismatch.reply_message is None

    # 9. Source tag leakage to Jiang Jiang confirmation -> status failed
    fake_gen_leak = FakeOrchestratorLlmGenerator(
        responses=[
            "用户报告实验结果与论文一致、姜姜确认实验结果与论文一致；"
            "to_verify：仍需核验 (•̀ᴗ•́)و ̑̑。"
        ]
    )
    orch_leak = ResearchConversationOrchestrator(llm_generator=fake_gen_leak)
    conv_leak = ResearchConversationModel(
        id="conv-p1-leak", profile_data={}, messages_data=[]
    )
    db_session.add(conv_leak)
    db_session.commit()

    resp_leak = orch_leak.process_message(
        "conv-p1-leak",
        SendOrchestratorMessageRequest(
            message="我观察到本次实验结果与论文结果一致，但还没有完成核验。"
        ),
        db_session,
    )
    assert resp_leak.status == "failed"
    assert resp_leak.reply_message is None

    # 10. Matching category 2 user evidence -> status completed
    fake_gen_cat2 = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告指标达到论文基线；to_verify：仍需核验 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_cat2 = ResearchConversationOrchestrator(llm_generator=fake_gen_cat2)
    conv_cat2 = ResearchConversationModel(
        id="conv-p1-cat2", profile_data={}, messages_data=[]
    )
    db_session.add(conv_cat2)
    db_session.commit()

    resp_cat2 = orch_cat2.process_message(
        "conv-p1-cat2",
        SendOrchestratorMessageRequest(
            message="我观察到本次实验指标达到论文基线，但还没有完成核验。"
        ),
        db_session,
    )
    assert resp_cat2.status == "completed"
    assert resp_cat2.reply_message is not None
    assert "fact：用户报告指标达到论文基线" in resp_cat2.reply_message.content

    # 11. Fine-grained fingerprint mismatch in orchestrator -> status failed, no advancement
    fake_gen_fp_mis = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告复现指标与论文指标一致；to_verify：仍需核验 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_fp_mis = ResearchConversationOrchestrator(llm_generator=fake_gen_fp_mis)
    conv_fp_mis = ResearchConversationModel(
        id="conv-p1-fp-mis", profile_data={}, messages_data=[]
    )
    db_session.add(conv_fp_mis)
    db_session.commit()

    resp_fp_mis = orch_fp_mis.process_message(
        "conv-p1-fp-mis",
        SendOrchestratorMessageRequest(
            message="我观察到本次实验结果与论文结果一致，但还没有完成核验。"
        ),
        db_session,
    )
    assert resp_fp_mis.status == "failed"
    assert resp_fp_mis.reply_message is None
    assert resp_fp_mis.state.last_status == "failed"
    assert resp_fp_mis.state.current_stage == "research_need"
    assert resp_fp_mis.state.subtasks.need_defined is False
    state_in_db_fp = orch_fp_mis.get_state_model("conv-p1-fp-mis", db_session)
    assert state_in_db_fp.current_plan is None
    assert len(state_in_db_fp.plan_history or []) == 0
    profiles_fp = orch_fp_mis.get_learner_profiles("conv-p1-fp-mis", db_session)
    assert len(profiles_fp.history) == 0

    # 12. Non-assertive user question in orchestrator -> status failed, no advancement
    fake_gen_q = FakeOrchestratorLlmGenerator(
        responses=["fact：用户报告实验结果与论文结果一致；to_verify：仍需核验 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_q = ResearchConversationOrchestrator(llm_generator=fake_gen_q)
    conv_q = ResearchConversationModel(id="conv-p1-q", profile_data={}, messages_data=[])
    db_session.add(conv_q)
    db_session.commit()

    resp_q = orch_q.process_message(
        "conv-p1-q",
        SendOrchestratorMessageRequest(message="实验结果是否与论文结果一致？"),
        db_session,
    )
    assert resp_q.status == "failed"
    assert resp_q.reply_message is None
    assert resp_q.state.last_status == "failed"
    assert resp_q.state.current_stage == "research_need"
    assert resp_q.state.subtasks.need_defined is False
    state_in_db_q = orch_q.get_state_model("conv-p1-q", db_session)
    assert state_in_db_q.current_plan is None
    assert len(state_in_db_q.plan_history or []) == 0
    profiles_q = orch_q.get_learner_profiles("conv-p1-q", db_session)
    assert len(profiles_q.history) == 0

    # 13. Question containing '跑通过' in orchestrator -> status completed
    fake_gen_q_run = FakeOrchestratorLlmGenerator(
        responses=["你亲手用 PyTorch Geometric 跑通过 Cora 数据集吗？(｡･ω･｡)"]
    )
    orch_q_run = ResearchConversationOrchestrator(llm_generator=fake_gen_q_run)
    conv_q_run = ResearchConversationModel(id="conv-p1-qrun", profile_data={}, messages_data=[])
    db_session.add(conv_q_run)
    db_session.commit()

    resp_q_run = orch_q_run.process_message(
        "conv-p1-qrun",
        SendOrchestratorMessageRequest(message="你好姜姜，我想开始科研"),
        db_session,
    )
    assert resp_q_run.status == "completed"
    assert resp_q_run.reply_message is not None

    # 14. Mastery assertion from learning context -> status failed, no advancement
    fake_gen_mast = FakeOrchestratorLlmGenerator(
        responses=["这说明你的线性代数和谱图论基本功已经很扎实了 (•̀ᴗ•́)و ̑̑。"]
    )
    orch_mast = ResearchConversationOrchestrator(llm_generator=fake_gen_mast)
    conv_mast = ResearchConversationModel(id="conv-p1-mast", profile_data={}, messages_data=[])
    db_session.add(conv_mast)
    db_session.commit()

    resp_mast = orch_mast.process_message(
        "conv-p1-mast",
        SendOrchestratorMessageRequest(message="你好姜姜，我想开始科研"),
        db_session,
    )
    assert resp_mast.status == "failed"
    assert resp_mast.reply_message is None
    assert resp_mast.state.last_status == "failed"
    assert resp_mast.state.current_stage == "research_need"
    assert resp_mast.state.subtasks.need_defined is False

    # 15. Capability/entrance inference from learning context -> status failed, no advancement
    for raw_resp in [
        "你已经有用 GCN 做节点分类的实践经验 (｡･ω･｡)。",
        "这说明你已经具备做比较深入研究的入口了 (•̀ᴗ•́)و ̑̑。",
    ]:
        orch_cap = ResearchConversationOrchestrator(
            llm_generator=FakeOrchestratorLlmGenerator(responses=[raw_resp])
        )
        cid = f"conv-cap-{abs(hash(raw_resp))}"
        conv_cap = ResearchConversationModel(id=cid, profile_data={}, messages_data=[])
        db_session.add(conv_cap)
        db_session.commit()
        resp_cap = orch_cap.process_message(
            cid,
            SendOrchestratorMessageRequest(message="你好姜姜，我想开始科研"),
            db_session,
        )
        assert resp_cap.status == "failed"
        assert resp_cap.reply_message is None
        assert resp_cap.state.last_status == "failed"
        assert resp_cap.state.current_stage == "research_need"
        assert resp_cap.state.subtasks.need_defined is False
        assert resp_cap.state.completed_stages == []


def test_s3_stage_transition_mode_selection_and_safety_regression(db_session: Session) -> None:
    """Regression test for R4 Gate 2 S3:
    stage transition must not be forced into strict learning mode.
    """
    # 1. Mode selection regression: stage transition template has is_learning_record_mode=False
    conv_id = "conv-s3-mode-sel"
    conv = ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    orch = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    ctx = LearningContextInput(
        learned_content="图卷积网络(GCN)数学推导与节点分类",
        learning_progress="完成理论推导，准备开展真实实验",
    )
    orch.update_learning_context(conv_id, ctx, db_session)

    state_model = db_session.get(ResearchOrchestratorStateModel, conv_id)
    subtasks = dict(state_model.subtasks or {})
    subtasks["need_defined"] = True
    state_model.subtasks = subtasks
    db_session.commit()

    user_confirm = "好的，就这个方向，没问题，确认进入下一步！"
    prompt_data = orch._select_prompt_template(
        conv_id,
        "research_need",
        subtasks,
        user_confirm,
        is_confirmed=True,
        db=db_session,
        owned_ids=None,
    )
    assert prompt_data.get("template_name") == "stage_transition"
    assert prompt_data.get("is_learning_record_mode") is False

    # 2. Global safety does not regress: even with learning_record_mode=False
    for forbidden_claim in [
        "你具备良好的科研能力，可以放心进入下一阶段 (｡･ω･｡)。",
        "你已经掌握了研究方法，因此研究计划已完成 (｡･ω･｡)。",
        "实验结果与论文一致，所以已经复现成功 (｡･ω･｡)。",
    ]:
        fake_gen_unsafe = FakeOrchestratorLlmGenerator(responses=[forbidden_claim])
        orch_unsafe = ResearchConversationOrchestrator(llm_generator=fake_gen_unsafe)
        conv_unsafe_id = f"conv-unsafe-{abs(hash(forbidden_claim))}"
        conv_unsafe = ResearchConversationModel(
            id=conv_unsafe_id, profile_data={}, messages_data=[]
        )
        db_session.add(conv_unsafe)
        db_session.commit()

        state_u = ResearchOrchestratorStateModel(
            conversation_id=conv_unsafe_id,
            current_stage="research_need",
            completed_stages=[],
            subtasks={"need_defined": True, "profile_ready": False, "plan_generated": False},
            direction_history=[],
            plan_history=[],
        )
        db_session.add(state_u)
        db_session.commit()

        resp_u = orch_unsafe.process_message(
            conv_unsafe_id,
            SendOrchestratorMessageRequest(message=user_confirm),
            db_session,
        )
        assert resp_u.status == "failed"
        assert resp_u.reply_message is None
        assert resp_u.state.current_stage == "research_need"
        assert "research_need" not in resp_u.state.completed_stages


def test_s3_stage_transition_source_scope_integration(db_session: Session) -> None:
    """Integration: stage_transition completed reply must deterministically inject
    source_scope prefix.

    - Provider output containing technical framework gets source_scope prefix prepended.
    - reply_message contains both the source_scope prefix and Provider original text.
    - stage advances from research_need to research_plan.
    - Provider failure or violation (capability / false reproduction) still fails immediately.
    """
    user_confirm = "好的，就这个方向，没问题，确认进入下一步！"

    # Case A: Provider outputs technical framework -> Completed response must contain source_scope
    resp_raw_provider = (
        "# 阶段跃迁确认 (＾▽＾)\n\n"
        "收到你的确认，我们正式从「研究需求确定」进入「研究计划生成」阶段。\n\n"
        "**已完成的工作**\n"
        "- 确定核心研究主题：图卷积神经网络在生物分子图性质预测上的应用\n"
        "- 明确研究问题框架：分子图表示 + 图卷积消息传递 + 整图读出 + 性质预测\n\n"
        "设备配置直接影响实验方案设计。很多分子数据集规模不大，CPU也能跑。\n\n"
        "请告知你的显卡配置 (｡･ω･｡)"
    )
    fake_gen_succ = FakeOrchestratorLlmGenerator(responses=[resp_raw_provider])
    orch_succ = ResearchConversationOrchestrator(llm_generator=fake_gen_succ)
    conv_succ_id = "conv-s3-succ-scope"
    conv_succ = ResearchConversationModel(id=conv_succ_id, profile_data={}, messages_data=[])
    db_session.add(conv_succ)
    db_session.commit()
    state_s = ResearchOrchestratorStateModel(
        conversation_id=conv_succ_id,
        current_stage="research_need",
        completed_stages=[],
        subtasks={"need_defined": True, "profile_ready": False, "plan_generated": False},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_s)
    db_session.commit()

    # Test via stream_message to check SSE thinking -> completed
    events = list(
        orch_succ.stream_message(
            conv_succ_id,
            SendOrchestratorMessageRequest(message=user_confirm),
            db_session,
        )
    )
    event_names = [
        line.split(":", 1)[1].strip()
        for ev in events
        for line in ev.strip().split("\n")
        if line.startswith("event:")
    ]
    assert event_names == ["thinking", "completed"]

    state_after = orch_succ.get_or_create_state(conv_succ_id, db_session)
    assert state_after.current_stage == "research_plan"
    assert "research_need" in state_after.completed_stages

    # Extract final reply content
    completed_event_str = [ev for ev in events if "event: completed" in ev][0]
    data_line = [ln for ln in completed_event_str.split("\n") if ln.startswith("data:")][0]
    payload = json.loads(data_line.split(":", 1)[1].strip())
    final_reply = payload["reply_message"]["content"]

    # 1. source_scope prefix must appear before technical content
    expected_scope_needle = "尚未执行正式检索"
    assert expected_scope_needle in final_reply
    scope_idx = final_reply.find(expected_scope_needle)
    tech_idx = final_reply.find("设备配置直接影响实验方案设计")
    assert scope_idx != -1
    assert tech_idx != -1
    assert scope_idx < tech_idx, "source_scope prefix must appear before technical text"

    # 2. reply_message retains Provider original text
    assert "很多分子数据集规模不大，CPU也能跑" in final_reply

    # Case B: Provider fails or violates boundary rules -> MUST FAIL (no completed masking)
    for bad_response in [
        "你已经具备科研能力，可以直接推进 (｡･ω･｡)。",
        "实验结果与论文一致，所以已经复现成功 (｡･ω･｡)。",
    ]:
        fake_gen_fail = FakeOrchestratorLlmGenerator(responses=[bad_response])
        orch_fail = ResearchConversationOrchestrator(llm_generator=fake_gen_fail)
        conv_fail_id = f"conv-s3-fail-{abs(hash(bad_response))}"
        conv_fail = ResearchConversationModel(id=conv_fail_id, profile_data={}, messages_data=[])
        db_session.add(conv_fail)
        db_session.commit()
        state_f = ResearchOrchestratorStateModel(
            conversation_id=conv_fail_id,
            current_stage="research_need",
            completed_stages=[],
            subtasks={"need_defined": True, "profile_ready": False, "plan_generated": False},
            direction_history=[],
            plan_history=[],
        )
        db_session.add(state_f)
        db_session.commit()

        stream_events = list(
            orch_fail.stream_message(
                conv_fail_id,
                SendOrchestratorMessageRequest(message=user_confirm),
                db_session,
            )
        )
        stream_event_names = [
            line.split(":", 1)[1].strip()
            for ev in stream_events
            for line in ev.strip().split("\n")
            if line.startswith("event:")
        ]
        assert stream_event_names == ["thinking", "failed"]

        state_f_after = orch_fail.get_or_create_state(conv_fail_id, db_session)
        assert state_f_after.current_stage == "research_need"
        assert "research_need" not in state_f_after.completed_stages


def test_select_prompt_template_learning_record_mode_isolation(db_session: Session) -> None:
    """Verify strict mode follows whether the selected template consumes records."""
    fake_gen = FakeOrchestratorLlmGenerator()
    orch = ResearchConversationOrchestrator(llm_generator=fake_gen)
    conv_id = "conv-mode-isolation"
    conv = ResearchConversationModel(
        id=conv_id,
        profile_data={},
        messages_data=[],
    )
    db_session.add(conv)
    db_session.commit()
    orch.update_learning_context(
        conv_id,
        LearningContextInput(
            learned_content="图卷积神经网络(GCN)",
            learning_progress="已完成",
        ),
        db_session,
    )

    # 1. welcome_and_bridge -> is_learning_record_mode is True
    tmpl_welcome = orch._select_prompt_template(
        conv_id,
        current_stage="research_need",
        subtasks={},
        user_message="你好姜姜",
        is_confirmed=False,
        db=db_session,
        owned_ids=None,
    )
    assert tmpl_welcome["template_name"] == "welcome_and_bridge"
    assert tmpl_welcome["is_learning_record_mode"] is True

    # 2. need_clarification must not consume learning records; S1 owns that bridge.
    tmpl_clarify = orch._select_prompt_template(
        conv_id,
        current_stage="research_need",
        subtasks={},
        user_message="我想做图卷积神经网络在生物分子图性质预测上的应用",
        is_confirmed=False,
        db=db_session,
        owned_ids=None,
    )
    assert tmpl_clarify["template_name"] == "need_clarification"
    assert tmpl_clarify["is_learning_record_mode"] is False
    assert "图卷积神经网络(GCN)" not in tmpl_clarify["user_prompt"]


def test_orchestrator_scope_prefix_injection_per_template(db_session: Session) -> None:
    """Verify that orchestrator injects template-specific scope prefix deterministically."""
    fake_gen = FakeOrchestratorLlmGenerator(
        responses=[
            "欢迎开启科研探索！这里有一些方向建议 (｡･ω･｡)。",
            "这是关于分子图性质预测的技术细节 (｡･ω･｡)。",
        ]
    )
    orch = ResearchConversationOrchestrator(llm_generator=fake_gen)
    conv_id = "conv-scope-prefix-inject"
    conv = ResearchConversationModel(
        id=conv_id,
        profile_data={},
        messages_data=[],
    )
    db_session.add(conv)
    db_session.commit()
    orch.update_learning_context(
        conv_id,
        LearningContextInput(
            learned_content="图卷积神经网络(GCN)",
            learning_progress="已完成",
        ),
        db_session,
    )

    # S1: Welcome message
    resp_s1 = orch.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="你好姜姜，我刚学完图神经网络，想开始做科研"),
        db_session,
    )
    assert resp_s1.reply_message is not None
    assert resp_s1.reply_message.content.startswith(RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME)
    assert "已确认方向" not in resp_s1.reply_message.content

    # S2: Clarification message
    resp_s2 = orch.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="我想做图卷积神经网络在生物分子图性质预测上的应用"),
        db_session,
    )
    assert resp_s2.reply_message is not None
    assert resp_s2.reply_message.content.startswith(RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION)
    assert "探索方向" in resp_s2.reply_message.content
