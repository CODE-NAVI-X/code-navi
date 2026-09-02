"""Tests for R3: Learning-to-Research Bridge.

Covers:
1. Learning input generates 5 dynamic cards and quotes context in Welcome prompt;
2. Empty state returns 200 and [] cards without hallucinating learning records;
3. Resumption and learning increment tracking (first consumption vs updates, failure rollback);
4. Custom direction allows exploration with prerequisite gap notes;
5. Hardware constraints guide lightweight alternatives without fake claims;
6. API contracts (extra=forbid -> 422, cross-owner -> 404).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.auth.dependencies import CurrentPrincipal, get_optional_principal
from code_navi.db import Base, get_db
from code_navi.research.conversation_orchestrator import (
    OrchestratorLlmOutcome,
    ResearchConversationOrchestrator,
    generate_dynamic_direction_cards,
)
from code_navi.research.conversation_orchestrator_schemas import (
    LearnerProfileUpdateRequest,
    LearningContextInput,
    SendOrchestratorMessageRequest,
)
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchOrchestratorStateModel,
)
from code_navi.server import app


class FakeBridgeLlmGenerator:
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
                reply_text="姜姜为你提供科研协助 (＾▽＾)。",
            )
        resp = self.responses.pop(0)
        if isinstance(resp, OrchestratorLlmOutcome):
            return resp
        if isinstance(resp, Exception):
            return OrchestratorLlmOutcome(status="failed", reason=str(resp))
        return OrchestratorLlmOutcome(status="generated", reply_text=resp)


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_bridge.db"
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


def test_visual_learning_input_generates_five_dynamic_cards_and_welcome_prompt(
    db_session,
) -> None:
    """1. Visual learning input produces 5 dynamic cards and quotes context in Welcome prompt."""
    fake_gen = FakeBridgeLlmGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_gen)

    conv = ResearchConversationModel(id="conv-bridge-cv", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Set visual learning context
    orchestrator.update_learning_context(
        "conv-bridge-cv",
        LearningContextInput(
            learned_content="学习了卷积神经网络基础、目标检测与特征金字塔",
            learning_progress="已完成图像分类实验，正在探索轻量目标检测",
        ),
        db_session,
    )

    # Fetch dynamic direction cards
    cards_resp = orchestrator.get_direction_cards("conv-bridge-cv", db_session)
    assert len(cards_resp.cards) == 5
    # Verify cards are CV-specific and not a fixed trivial list
    card_titles = [c.title for c in cards_resp.cards]
    assert any("目标检测" in t or "视觉" in t or "图像" in t for t in card_titles)
    # Check card fields
    for card in cards_resp.cards:
        assert card.id
        assert card.title
        assert card.description
        assert isinstance(card.is_recommended, bool)

    # Process opening greeting message
    resp = orchestrator.process_message(
        "conv-bridge-cv",
        SendOrchestratorMessageRequest(message="你好，开始科研"),
        db_session,
    )
    assert resp.status == "completed"
    assert len(fake_gen.calls) == 1
    call = fake_gen.calls[0]
    user_prompt = call["user_prompt"]
    assert "学习了卷积神经网络基础" in user_prompt
    assert "已完成图像分类实验" in user_prompt
    assert "【基于学习内容动态生成的推荐研究方向】" in user_prompt


def test_empty_learning_state_returns_200_and_empty_cards_without_hallucination(
    db_session,
) -> None:
    """2. Empty learning state returns 200, [] cards, and does not forge learning records."""
    fake_gen = FakeBridgeLlmGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_gen)

    conv = ResearchConversationModel(id="conv-bridge-empty", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Empty PUT
    ctx_state = orchestrator.update_learning_context(
        "conv-bridge-empty",
        LearningContextInput(learned_content=None, learning_progress=None),
        db_session,
    )
    assert ctx_state.learned_content is None
    assert ctx_state.learning_progress is None

    # Empty GET cards
    cards_resp = orchestrator.get_direction_cards("conv-bridge-empty", db_session)
    assert cards_resp.cards == []
    assert cards_resp.learned_content is None

    # Direct helper check
    assert generate_dynamic_direction_cards(None, None) == []
    assert generate_dynamic_direction_cards("", "   ") == []

    # Process message in empty state
    orchestrator.process_message(
        "conv-bridge-empty",
        SendOrchestratorMessageRequest(message="你好，开始科研"),
        db_session,
    )
    assert len(fake_gen.calls) == 1
    call = fake_gen.calls[0]
    assert "暂无学习端输入（空态）" in call["user_prompt"]
    assert "暂无学习进度" in call["user_prompt"]


def test_learning_context_snapshot_tracking_and_incremental_updates(
    db_session,
) -> None:
    """3. Test first consumption has no increment, but subsequent updates include increment."""
    fake_gen = FakeBridgeLlmGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_gen)

    conv = ResearchConversationModel(id="conv-bridge-inc", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Step 1: Set initial learning context
    orchestrator.update_learning_context(
        "conv-bridge-inc",
        LearningContextInput(
            learned_content="学习了基础线性代数与图卷积概念",
            learning_progress="已完成图卷积前置章节",
        ),
        db_session,
    )

    # First turn: opening message
    resp1 = orchestrator.process_message(
        "conv-bridge-inc",
        SendOrchestratorMessageRequest(message="你好，开始科研"),
        db_session,
    )
    assert resp1.status == "completed"
    assert len(fake_gen.calls) == 1
    # First turn must NOT claim "学习端输入有更新" or "增量"
    assert "增量更新" not in fake_gen.calls[0]["user_prompt"]
    assert "学习端输入更新" not in fake_gen.calls[0]["user_prompt"]

    # Step 2: Same input in second message -> no increment
    fake_gen.calls.clear()
    resp2 = orchestrator.process_message(
        "conv-bridge-inc",
        SendOrchestratorMessageRequest(message="我想了解更多关于图节点分类的思路"),
        db_session,
    )
    assert resp2.status == "completed"
    assert len(fake_gen.calls) == 1
    assert "增量更新" not in fake_gen.calls[0]["user_prompt"]

    # Step 3: Producer updates learning context with new progress
    orchestrator.update_learning_context(
        "conv-bridge-inc",
        LearningContextInput(
            learned_content="学习了基础线性代数与图卷积概念，新增图注意力网络 GAT 与异质图",
            learning_progress="已完成 GAT 实践代码与多头注意力作业",
        ),
        db_session,
    )

    # Step 4: Next conversation turn receives learning increment context
    fake_gen.calls.clear()
    resp3 = orchestrator.process_message(
        "conv-bridge-inc",
        SendOrchestratorMessageRequest(message="我回来了，我们继续讨论"),
        db_session,
    )
    assert resp3.status == "completed"
    assert len(fake_gen.calls) == 1
    user_prompt3 = fake_gen.calls[0]["user_prompt"]
    assert "学习端输入" in user_prompt3
    assert "新增图注意力网络 GAT" in user_prompt3 or "GAT 实践代码" in user_prompt3


def test_learning_increment_snapshot_does_not_advance_on_provider_failure(
    db_session,
) -> None:
    """3b. If Provider fails, last_consumed_snapshot must NOT be updated."""
    # First call succeeds, second fails, third succeeds
    fake_gen = FakeBridgeLlmGenerator(
        responses=[
            "欢迎来到科研端 (＾▽＾)！",
            Exception("DeepSeek connection timed out"),
            "姜姜已恢复连接 (•̀ᴗ•́)و ̑̑！",
        ]
    )
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_gen)

    conv = ResearchConversationModel(id="conv-bridge-fail-snap", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Initial learning input
    orchestrator.update_learning_context(
        "conv-bridge-fail-snap",
        LearningContextInput(
            learned_content="初学 Python",
            learning_progress="10%",
        ),
        db_session,
    )
    # 1. Turn 1 succeeds
    r1 = orchestrator.process_message(
        "conv-bridge-fail-snap",
        SendOrchestratorMessageRequest(message="你好，开始科研"),
        db_session,
    )
    assert r1.status == "completed"

    # Update learning input
    orchestrator.update_learning_context(
        "conv-bridge-fail-snap",
        LearningContextInput(
            learned_content="初学 Python，新增 PyTorch 张量操作与自动求导",
            learning_progress="40%",
        ),
        db_session,
    )

    # 2. Turn 2 fails due to Provider error
    r2 = orchestrator.process_message(
        "conv-bridge-fail-snap",
        SendOrchestratorMessageRequest(message="继续探讨"),
        db_session,
    )
    assert r2.status == "failed"

    # 3. Turn 3 succeeds via retry-last; increment must STILL be passed because turn 2 failed!
    r3 = orchestrator.retry_last_message("conv-bridge-fail-snap", db_session)
    assert r3.status == "completed"
    assert len(fake_gen.calls) == 3
    # Call 3 must contain the unconsumed increment
    call3_prompt = fake_gen.calls[2]["user_prompt"]
    assert "PyTorch 张量操作" in call3_prompt


def test_custom_direction_with_large_knowledge_gap_allows_exploration(
    db_session,
) -> None:
    """4. Custom direction with large gap provides gap notes but does not block exploration."""
    fake_gen = FakeBridgeLlmGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_gen)

    conv = ResearchConversationModel(id="conv-bridge-custom", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    orchestrator.update_learning_context(
        "conv-bridge-custom",
        LearningContextInput(
            learned_content="刚学完基础 Python 语法与简单线性回归",
            learning_progress="第 1 周入门",
        ),
        db_session,
    )

    # User proposes an advanced custom direction
    resp = orchestrator.process_message(
        "conv-bridge-custom",
        SendOrchestratorMessageRequest(
            message="我想做基于大语言模型的多模态具身智能 Agent 导航与决策"
        ),
        db_session,
    )
    assert resp.status == "completed"
    assert resp.state.current_stage == "research_need"
    assert len(fake_gen.calls) == 1
    call = fake_gen.calls[0]
    # Check that need_clarification prompt has rules regarding gentle prerequisite gap notes
    assert "需求澄清" in call["system_prompt"]
    assert "前置知识缺口" in call["system_prompt"]
    assert "不阻止" in call["system_prompt"] or "尊重用户的探索意愿" in call["system_prompt"]


def test_hardware_constraints_in_profile_guides_lightweight_or_rental_options(
    db_session,
) -> None:
    """5. Limited hardware profile in research_plan guides lightweight models or renting compute."""
    fake_gen = FakeBridgeLlmGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=fake_gen)

    conv = ResearchConversationModel(id="conv-bridge-hw", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    state = ResearchOrchestratorStateModel(
        conversation_id="conv-bridge-hw",
        current_stage="research_plan",
        completed_stages=["research_need"],
        subtasks={"need_defined": True, "profile_ready": False, "plan_generated": False},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state)
    db_session.commit()

    # User has limited hardware (GTX 1650 4GB)
    orchestrator.update_learner_profile(
        "conv-bridge-hw",
        LearnerProfileUpdateRequest(hardware="笔记本 GTX 1650 4GB 显存，16GB 内存"),
        db_session,
    )

    resp = orchestrator.process_message(
        "conv-bridge-hw",
        SendOrchestratorMessageRequest(message="我想在我的电脑上跑大模型微调实验"),
        db_session,
    )
    assert resp.status == "completed"
    assert len(fake_gen.calls) == 1
    call = fake_gen.calls[0]
    system_prompt = call["system_prompt"]
    user_prompt = call["user_prompt"]
    assert "GTX 1650 4GB" in user_prompt
    # System rules must instruct lightweight/batch size/compute rental
    assert "≤8GB" in system_prompt or "显存受限" in system_prompt or "租用算力" in system_prompt


def test_learning_context_api_extra_fields_forbidden(tmp_path) -> None:
    """6a. Unknown extra fields on LearningContextInput return 422."""
    db_file = tmp_path / "test_api_forbid.db"
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
    client = TestClient(app)

    db = TestingSession()
    conv = ResearchConversationModel(id="conv-api-forbid", profile_data={}, messages_data=[])
    db.add(conv)
    db.commit()
    conv_id = conv.id
    db.close()

    resp = client.put(
        f"/api/v1/research/conversations/{conv_id}/orchestrator/learning-context",
        json={
            "learned_content": "图卷积网络",
            "learning_progress": "50%",
            "illegal_extra_field": "disallowed",
        },
    )
    assert resp.status_code == 422
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_learning_context_api_cross_owner_returns_404(tmp_path) -> None:
    """6b. Cross-owner access to learning-context returns 404."""
    db_file = tmp_path / "test_api_owner.db"
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

    def override_auth() -> CurrentPrincipal:
        return CurrentPrincipal(
            principal_id="user-b",
            user_id="user-b",
            mode="authenticated",
            email_verified=True,
            session_id="sess-test",
            role="user",
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_optional_principal] = override_auth
    client = TestClient(app)

    db = TestingSession()
    conv = ResearchConversationModel(
        id="conv-api-owner-a",
        owner_principal_id="user-a",
        profile_data={},
        messages_data=[],
    )
    db.add(conv)
    db.commit()
    conv_id = conv.id
    db.close()

    resp = client.put(
        f"/api/v1/research/conversations/{conv_id}/orchestrator/learning-context",
        json={"learned_content": "内容", "learning_progress": "进度"},
    )
    assert resp.status_code == 404

    get_resp = client.get(
        f"/api/v1/research/conversations/{conv_id}/orchestrator/learning-context"
    )
    assert get_resp.status_code == 404

    app.dependency_overrides.clear()
    test_engine.dispose()

