"""Tests for the Four-Stage State Machine in Research Conversation Orchestration."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.conversation_orchestrator import (
    ResearchConversationOrchestrator,
    detect_confirmation_intent,
    detect_direction_change_intent,
    is_history_inquiry,
)
from code_navi.research.conversation_orchestrator_schemas import (
    SendOrchestratorMessageRequest,
)
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchOrchestratorStateModel,
)


@pytest.fixture
def db_session(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test_sm.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_intent_detection_confirmation() -> None:
    assert detect_confirmation_intent("可以，我觉得这个方向很好")
    assert detect_confirmation_intent("继续吧，进入下一步")
    assert detect_confirmation_intent("就这样")
    assert detect_confirmation_intent("好的，没问题")
    assert detect_confirmation_intent("行，走下一步")

    # Vague, hesitant, negative
    assert not detect_confirmation_intent("我想再想想")
    assert not detect_confirmation_intent("不太对，需要改改")
    assert not detect_confirmation_intent("等等，不确定")
    assert not detect_confirmation_intent("好像不行")


def test_intent_detection_direction_change() -> None:
    assert detect_direction_change_intent("我想换个方向")
    assert detect_direction_change_intent("重新选方向")
    assert detect_direction_change_intent("换方向做别的")

    # Asking about history should NOT be treated as direction change
    assert not detect_direction_change_intent("之前说了什么？")
    assert not detect_direction_change_intent("我们刚才讨论了哪个方向？")
    assert is_history_inquiry("之前说了什么？")
    assert is_history_inquiry("我们刚才讨论了哪个方向？")


def test_state_machine_advancement_requires_subtasks_and_confirmation(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-sm-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Initial state
    state = orchestrator.get_or_create_state("conv-sm-1", db_session)
    assert state.current_stage == "research_need"
    assert "research_need" not in state.completed_stages

    # 1. User says "可以", but need_defined is False -> does NOT advance
    resp = orchestrator.process_message(
        "conv-sm-1",
        SendOrchestratorMessageRequest(message="可以，继续吧"),
        db_session,
    )
    assert resp.state.current_stage == "research_need"

    # 2. Mark need_defined = True, but user message is hesitant -> does NOT advance
    state_model = db_session.get(ResearchOrchestratorStateModel, "conv-sm-1")
    state_model.subtasks = {"need_defined": True}
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sm-1",
        SendOrchestratorMessageRequest(message="我想再想想，等等看"),
        db_session,
    )
    assert resp.state.current_stage == "research_need"

    # 3. need_defined is True AND user confirms -> advances to research_plan
    resp = orchestrator.process_message(
        "conv-sm-1",
        SendOrchestratorMessageRequest(message="可以，确认这个需求，我们继续！"),
        db_session,
    )
    assert resp.state.current_stage == "research_plan"
    assert "research_need" in resp.state.completed_stages


def test_state_machine_direction_change_resets_to_research_need(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-sm-2", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Move to research_execution
    state_model = ResearchOrchestratorStateModel(
        conversation_id="conv-sm-2",
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={"need_defined": True, "profile_ready": True, "plan_generated": True},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_model)
    db_session.commit()

    # User asks to change direction
    resp = orchestrator.process_message(
        "conv-sm-2",
        SendOrchestratorMessageRequest(message="我想换个方向，做大模型多模态检索"),
        db_session,
    )
    assert resp.state.current_stage == "research_need"
    assert len(resp.state.direction_history) == 1
    assert (
        "大模型多模态检索" in resp.state.direction_history[0].direction
        or "换" in resp.state.direction_history[0].direction
    )


def test_asking_about_history_does_not_reset_stage(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-sm-3", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    state_model = ResearchOrchestratorStateModel(
        conversation_id="conv-sm-3",
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={"need_defined": True, "profile_ready": True, "plan_generated": True},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_model)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sm-3",
        SendOrchestratorMessageRequest(message="我们之前第一阶段选了什么方向？"),
        db_session,
    )
    # Must remain in research_execution
    assert resp.state.current_stage == "research_execution"
