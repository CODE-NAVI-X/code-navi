"""Tests for Learner Profile versioning, single paper, cards, and retry."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.conversation_orchestrator import (
    ResearchConversationOrchestrator,
    generate_dynamic_direction_cards,
)
from code_navi.research.conversation_orchestrator_schemas import (
    LearnerProfileUpdateRequest,
    LearningContextInput,
    SelectPaperRequest,
    SendOrchestratorMessageRequest,
)
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchLearnerProfileModel,
)


@pytest.fixture
def db_session(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test_lp.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_dynamic_direction_cards_not_fixed_to_cnn() -> None:
    # 1. GNN/Graph input
    gnn_cards = generate_dynamic_direction_cards("图神经网络与图卷积 GCN", "节点分类完成")
    assert len(gnn_cards) == 5
    assert any("图" in card.title or "图" in card.description for card in gnn_cards)
    assert not all("CNN" in card.title for card in gnn_cards)

    # 2. NLP/Transformer input
    nlp_cards = generate_dynamic_direction_cards(
        "Transformer 与自注意力机制", "词嵌入与文本生成"
    )
    assert len(nlp_cards) == 5
    assert any(
        "语言" in card.title or "注意力" in card.title or "文本" in card.title
        for card in nlp_cards
    )

    # 3. Empty input
    empty_cards = generate_dynamic_direction_cards(None, None)
    assert len(empty_cards) == 5


def test_learner_profile_versioning(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-lp-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Initial profile is empty
    resp = orchestrator.get_learner_profiles("conv-lp-1", db_session)
    assert resp.current_profile is None or resp.current_version is None

    # Update 1: Set hardware and python_env -> version 1
    resp1 = orchestrator.update_learner_profile(
        "conv-lp-1",
        LearnerProfileUpdateRequest(
            hardware="RTX 4060 8GB",
            python_env="Python 3.11",
            change_summary="填写硬件环境",
        ),
        db_session,
    )
    assert resp1.current_version == 1
    assert resp1.current_profile.hardware == "RTX 4060 8GB"
    assert len(resp1.history) == 1

    # Update 2: Update weekly_hours -> version 2
    resp2 = orchestrator.update_learner_profile(
        "conv-lp-1",
        LearnerProfileUpdateRequest(
            weekly_hours="15 小时/周",
            change_summary="补充每周投入时间",
        ),
        db_session,
    )
    assert resp2.current_version == 2
    assert resp2.current_profile.hardware == "RTX 4060 8GB"
    assert resp2.current_profile.weekly_hours == "15 小时/周"
    assert len(resp2.history) == 2

    # Check database rows
    rows = (
        db_session.query(ResearchLearnerProfileModel)
        .filter(ResearchLearnerProfileModel.conversation_id == "conv-lp-1")
        .order_by(ResearchLearnerProfileModel.version)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].is_current is False
    assert rows[1].is_current is True


def test_single_current_paper_and_usages(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-paper-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    paper_title = "Semi-Supervised Classification with Graph Convolutional Networks"

    # 1. Select paper 1 with replace -> becomes current paper
    orchestrator.select_paper(
        "conv-paper-1",
        SelectPaperRequest(
            paper_url="https://arxiv.org/abs/1609.02907",
            title=paper_title,
            purpose="replace",
        ),
        db_session,
    )
    resp1 = orchestrator.get_papers("conv-paper-1", db_session)
    assert resp1.current_paper is not None
    assert resp1.current_paper.title == paper_title
    assert len(resp1.paper_history) == 1

    # 2. Add paper 2 with compare -> current paper remains paper 1, paper 2 added to history
    orchestrator.select_paper(
        "conv-paper-1",
        SelectPaperRequest(
            paper_url="https://arxiv.org/abs/1710.10903",
            title="Graph Attention Networks",
            purpose="compare",
        ),
        db_session,
    )
    resp2 = orchestrator.get_papers("conv-paper-1", db_session)
    assert resp2.current_paper.title == paper_title
    assert len(resp2.paper_history) == 2

    # 3. Add paper 3 with replace -> current paper becomes paper 3
    orchestrator.select_paper(
        "conv-paper-1",
        SelectPaperRequest(
            paper_url="https://arxiv.org/abs/1710.10903",
            title="Graph Attention Networks",
            purpose="replace",
        ),
        db_session,
    )
    resp3 = orchestrator.get_papers("conv-paper-1", db_session)
    assert resp3.current_paper.title == "Graph Attention Networks"
    assert len(resp3.paper_history) == 3


def test_learning_context_persistence_and_empty_state(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-lc-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Empty state initially
    initial = orchestrator.get_learning_context("conv-lc-1", db_session)
    assert initial.learned_content is None
    assert initial.learning_progress is None

    # Put learning context
    updated = orchestrator.update_learning_context(
        "conv-lc-1",
        LearningContextInput(
            learned_content="PyTorch 卷积神经网络",
            learning_progress="已完成进阶实验",
        ),
        db_session,
    )
    assert updated.learned_content == "PyTorch 卷积神经网络"
    assert updated.learning_progress == "已完成进阶实验"


def test_failed_message_and_retry(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-fail-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Simulate a failed generation by forcing an error in generation hook or provider
    resp = orchestrator.process_message(
        "conv-fail-1",
        SendOrchestratorMessageRequest(message="帮我看看这个方案"),
        db_session,
        force_failure="Mock provider timeout error",
    )
    assert resp.status == "failed"
    assert resp.error == "Mock provider timeout error"
    assert resp.state.last_status == "failed"

    # Retrying the failed message
    retry_resp = orchestrator.retry_last_message("conv-fail-1", db_session)
    assert retry_resp.status == "completed"
    assert retry_resp.state.last_status == "completed"
