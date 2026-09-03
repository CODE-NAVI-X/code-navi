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
