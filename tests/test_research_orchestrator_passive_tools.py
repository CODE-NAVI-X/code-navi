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
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
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


class FakePassiveToolLlmGenerator:
    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
        from code_navi.research.conversation_orchestrator import OrchestratorLlmOutcome
        return OrchestratorLlmOutcome(
            status="generated",
            reply_text=f"姜姜为你解读工具输出 (＾▽＾)：\n\n{user_prompt}",
        )


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
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakePassiveToolLlmGenerator())
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
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakePassiveToolLlmGenerator())
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
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakePassiveToolLlmGenerator())
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


def test_study_recommendations_unconfirmed_requires_confirmation_and_does_not_forge_list(
    db_session,
) -> None:
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakePassiveToolLlmGenerator())
    conv = ResearchConversationModel(
        id="conv-pt-rec-unconfirmed",
        profile_data={"topic": "图卷积网络", "methods": ["GCN 节点分类"]},
        messages_data=[],
    )
    db_session.add(conv)
    db_session.commit()

    # User asks without explicit confirmation keywords
    resp = orchestrator.process_message(
        "conv-pt-rec-unconfirmed",
        SendOrchestratorMessageRequest(message="我该先学什么知识，有什么学习建议？"),
        db_session,
    )
    assert resp.reply_message.passive_tool_called == "study-recommendations"
    # Must truthfully state confirmation required, not return forged list
    assert (
        "需要用户明确确认" in resp.reply_message.content
        or "前置条件不足" in resp.reply_message.content
    )


def test_study_recommendations_confirmed_calls_service_with_confirmed_true(
    db_session,
) -> None:
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakePassiveToolLlmGenerator())
    conv = ResearchConversationModel(
        id="conv-pt-rec-confirmed",
        profile_data={"topic": "图卷积网络", "methods": ["GCN 节点分类"]},
        messages_data=[],
    )
    db_session.add(conv)
    db_session.commit()

    # User explicitly confirms
    resp = orchestrator.process_message(
        "conv-pt-rec-confirmed",
        SendOrchestratorMessageRequest(message="可以，我确认，推荐我该先学什么知识"),
        db_session,
    )
    assert resp.reply_message.passive_tool_called == "study-recommendations"
    assert (
        "前置知识点清单" in resp.reply_message.content
        or "掌握状态" in resp.reply_message.content
    )


def test_reproduction_evaluations_tool_empty_pipeline_state(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakePassiveToolLlmGenerator())
    conv = ResearchConversationModel(
        id="conv-pt-eval-empty",
        profile_data={"topic": "Transformer 文本分类"},
        messages_data=[],
    )
    db_session.add(conv)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-pt-eval-empty",
        SendOrchestratorMessageRequest(message="评估一下我的复现，准备得怎么样了，还差什么？"),
        db_session,
    )
    assert resp.reply_message.passive_tool_called == "reproduction-evaluations"
    # When no pipeline, must report lack of pipeline truthfully without asserting "准备度良好"
    assert "复现准备度" in resp.reply_message.content
    assert "尚未建立" in resp.reply_message.content or "缺少" in resp.reply_message.content
    assert "复现准备度良好" not in resp.reply_message.content
    assert "8GB" not in resp.reply_message.content
