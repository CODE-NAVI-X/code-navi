"""Tests for the 6 Passive Tools Deterministic Triggering and Multi-intent Clarification."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.conversation_orchestrator import (
    ResearchConversationOrchestrator,
    detect_passive_tool_intent,
)
from code_navi.research.conversation_orchestrator_schemas import (
    SendOrchestratorMessageRequest,
)
from code_navi.research.models import (
    ResearchConversationModel,
)


@pytest.fixture
def db_session(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test_pt.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_detect_single_passive_tool_intents() -> None:
    assert detect_passive_tool_intent("我现在进展如何，帮我总结一下") == ["stage-briefing"]
    assert detect_passive_tool_intent("我该先学什么知识，有什么学习建议？") == [
        "study-recommendations"
    ]
    assert detect_passive_tool_intent("这个方向难吗？难点在哪？") == [
        "topic-difficulty-analysis"
    ]
    assert detect_passive_tool_intent("帮我设计实验方案，怎么跑实验？") == ["experiment-design"]
    assert detect_passive_tool_intent("论文结构大纲怎么写，五段框架是什么？") == ["paper-blueprint"]
    assert detect_passive_tool_intent(
        "评估一下我的复现，准备得怎么样了，还差什么？"
    ) == ["reproduction-evaluations"]


def test_detect_multiple_tool_intents() -> None:
    intents = detect_passive_tool_intent("我现在进展如何？另外帮我设计实验方案怎么做？")
    assert len(intents) >= 2
    assert "stage-briefing" in intents
    assert "experiment-design" in intents


def test_multiple_intents_triggers_clarification_without_calling_tools(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-pt-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-pt-1",
        SendOrchestratorMessageRequest(message="我现在进展如何？顺便帮我设计实验方案怎么做？"),
        db_session,
    )
    # Must NOT call any passive tool directly; must clarify
    assert resp.reply_message.passive_tool_called is None
    assert (
        "先" in resp.reply_message.content
        or "澄清" in resp.reply_message.content
        or "想先" in resp.reply_message.content
    )


def test_single_intent_stage_briefing_triggers_tool(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(
        id="conv-pt-2",
        profile_data={"topic": "图卷积网络节点分类"},
        messages_data=[],
        context_provenance={"topic": "图神经网络", "summary": "学习了基础图卷积"},
    )
    db_session.add(conv)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-pt-2",
        SendOrchestratorMessageRequest(message="总结一下我们到哪了，我现在进展如何？"),
        db_session,
    )
    assert resp.reply_message.passive_tool_called == "stage-briefing"
    assert "图" in resp.reply_message.content or "进展" in resp.reply_message.content


def test_tool_empty_state_does_not_hallucinate(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    # Completely empty conversation without learning context or evidence
    conv = ResearchConversationModel(id="conv-pt-3", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-pt-3",
        SendOrchestratorMessageRequest(message="我现在进展如何？"),
        db_session,
    )
    assert resp.reply_message.passive_tool_called == "stage-briefing"
    # Should truthfully report absence of learning context / empty state
    assert (
        "暂无" in resp.reply_message.content
        or "未开始" in resp.reply_message.content
        or "开始" in resp.reply_message.content
    )
