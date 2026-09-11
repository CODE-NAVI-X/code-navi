"""Regression tests for the research-side CNN fixed demo flow."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.cnn_preset import (
    CNN_PRESET_DEMO_SOURCE,
    CNN_PRESET_PAPERS,
    is_cnn_preset_trigger,
)
from code_navi.research.conversation_orchestrator import ResearchConversationOrchestrator
from code_navi.research.conversation_orchestrator_schemas import (
    SendOrchestratorMessageRequest,
)
from code_navi.research.conversation_search_service import ResearchConversationSearchService
from code_navi.research.models import ResearchConversationModel


def test_cnn_preset_trigger_is_exact() -> None:
    assert is_cnn_preset_trigger("我想研究CNN")
    assert is_cnn_preset_trigger(" 我想研究CNN。 ")
    assert not is_cnn_preset_trigger("我想研究 CNN")
    assert not is_cnn_preset_trigger("我想研究CNN并帮我检索")


def test_cnn_preset_confirmation_persists_demo_bundle_and_current_paper(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'cnn_preset.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    conversation_id = "cnn-preset-integration"
    session.add(ResearchConversationModel(id=conversation_id, profile_data={}, messages_data=[]))
    session.commit()
    try:
        orchestrator = ResearchConversationOrchestrator(
            search_service=ResearchConversationSearchService(),
        )

        def send(text: str):
            return orchestrator.process_message(
                conversation_id,
                SendOrchestratorMessageRequest(message=text),
                session,
            )

        send("我想研究CNN")
        send("确认研究不同数据增强策略对 CNN SHAP 解释稳定性的影响")
        papers_reply = send("确认，按这个固定实验方案继续")
        assert "固定演示候选" in papers_reply.reply_message.content

        bundles = orchestrator.search_service.list_bundles(conversation_id, session)
        assert len(bundles) == 1
        assert bundles[0].query == ""
        assert bundles[0].queried_sources == []
        assert bundles[0].source_statuses[0].source == CNN_PRESET_DEMO_SOURCE
        assert [paper.title for paper in bundles[0].papers] == [
            str(item["title"]) for item in CNN_PRESET_PAPERS
        ]

        send("我选择第1篇论文")
        confirmed = send("确认，将这篇论文设为当前复现论文")
        assert "论文确认完成" in confirmed.reply_message.content

        papers = orchestrator.get_papers(conversation_id, session)
        assert papers.current_paper is not None
        assert papers.current_paper.title == str(CNN_PRESET_PAPERS[0]["title"])
        assert papers.current_paper.paper_url == str(CNN_PRESET_PAPERS[0]["url"])
        assert confirmed.state.current_stage == "research_analysis"
        assert confirmed.state.subtasks.paper_selected is True
    finally:
        session.close()
        engine.dispose()
