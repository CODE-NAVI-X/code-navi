"""Direction selection flow: domain-matched cards, no invented choices, closed loop.

Covers the three gaps behind the "你已选择的方向：图神经网络…" boundary failure:
1. direction cards must match the learning domain (图像/ViT is vision, not GNN);
2. the welcome prompt must forbid attributing an unconfirmed card choice to the
   user, and the attribution validator must still accept verbatim echoes of the
   user's own words (quoted or not) while blocking invented titles;
3. retrying a backend-initiated failed bridge welcome must regenerate the
   welcome instead of 409 "nothing to retry".
"""

from __future__ import annotations

import re
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.auth.rate_limiter import get_rate_limiter
from code_navi.db import Base, get_db
from code_navi.research.conversation_orchestrator import (
    OrchestratorLlmOutcome,
    ResearchConversationOrchestrator,
    generate_dynamic_direction_cards,
)
from code_navi.research.conversation_orchestrator_schemas import LearningContextState
from code_navi.research.conversation_prompt_templates import (
    build_welcome_prompt,
    validate_jiangjiang_output,
)
from code_navi.server import app


def _cards(learned: str, progress: str | None = None):
    return generate_dynamic_direction_cards(learned, progress)


def test_vit_image_learning_gets_vision_cards_not_gnn() -> None:
    """学 ViT 图像分类：方向卡必须是视觉/图像方向，绝不能是图神经网络。"""
    cards = _cards("ViT（Vision Transformer）图像分类", "完成基础学习")
    assert len(cards) == 5
    joined = " ".join(card.title for card in cards)
    assert "图神经网络" not in joined
    assert any(
        keyword in joined for keyword in ("图像", "视觉", "目标检测", "分割", "超分辨率", "多模态")
    )


def test_graph_learning_still_gets_gnn_cards() -> None:
    """图神经网络学习仍拿到 GNN 方向卡（显式图标记不受影响）。"""
    for learned in ("图卷积网络 GCN", "图神经网络消息传递机制", "图注意力网络 GAT"):
        cards = _cards(learned, "完成基础学习")
        assert len(cards) == 5
        assert all(card.id.startswith("dir-gnn-") for card in cards), learned


def test_image_only_learning_gets_vision_cards() -> None:
    """“图像分类”里的“图”不再被误判为图神经网络。"""
    cards = _cards("图像分类入门", None)
    assert all(card.id.startswith("dir-cv-") for card in cards)


def test_language_model_learning_gets_nlp_cards() -> None:
    cards = _cards("transformer 语言模型", None)
    assert all(card.id.startswith("dir-nlp-") for card in cards)


def test_unclassified_learning_falls_back_to_adaptive_cards() -> None:
    cards = _cards("社区发现算法", None)
    assert len(cards) == 5
    assert all(card.id.startswith("dir-adp-") for card in cards)


def test_welcome_prompt_forbids_attributing_unconfirmed_choice() -> None:
    """欢迎语规则必须禁止把方向卡片说成用户已选（用户未选择前只是选项）。"""
    prompt = build_welcome_prompt(
        LearningContextState(
            conversation_id="conv-x",
            learned_content="图卷积网络 GCN",
            learning_progress="完成基础学习",
        ),
        _cards("图卷积网络 GCN", "完成基础学习"),
    )
    rules = prompt["rules"]
    assert "严禁" in rules
    assert "你已选择" in rules  # 规则必须点名这类表述
    assert "逐字" in rules  # 引用用户选择时必须使用用户原词
    # 卡片由页面确定性渲染：模型不逐条罗列，也不得暴露"【卡片 N】"骨架字样
    assert "【卡片 1】" in rules
    assert "不要在回复中逐条罗列" in rules


def test_validator_accepts_quoted_echo_of_user_confirmed_choice() -> None:
    """用户确实选择后，模型带引号/连接词的回声不应被误拦；编造的仍要拦。"""
    evidence = ["我选择的研究方向是：图神经网络在引文网络上的节点分类"]

    ok, reason = validate_jiangjiang_output(
        "说明：以下内容基于学习端记录与通用技术概览，"
        "尚未执行正式检索；具体论文、实现细节和实验结论仍需在你确认后核验。\n"
        "好的，你已选择了「图神经网络在引文网络上的节点分类」，我们先明确节点分类的具体研究问题。",
        evidence_context=evidence,
    )
    assert ok, reason

    blocked, reason2 = validate_jiangjiang_output(
        "说明：以下内容基于学习端记录与通用技术概览，"
        "尚未执行正式检索；具体论文、实现细节和实验结论仍需在你确认后核验。\n"
        "好的，你已选择了「图对比学习与无监督表征」，我们先明确自监督预训练的具体研究问题。",
        evidence_context=evidence,
    )
    assert not blocked, reason2  # 用户从未说过该方向，编造选择必须被拦


class UnavailableWelcomeGenerator:
    def generate(self, **_kwargs) -> OrchestratorLlmOutcome:
        return OrchestratorLlmOutcome(status="unavailable", reason="Provider not configured")


class FakeBridgeWelcomeGenerator:
    """Minimal valid bridge-welcome renderer for retry tests."""

    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
        learned_match = re.search(r"已学内容：(.+)", user_prompt)
        progress_match = re.search(r"学习进度：(.+)", user_prompt)
        learned = learned_match.group(1).strip() if learned_match else None
        progress = progress_match.group(1).strip() if progress_match else None
        cards = generate_dynamic_direction_cards(learned, progress)
        preview = (
            f"我已经根据你的学习内容准备了 {len(cards)} 个可探索方向，"
            "可以在下方卡片里挑一个感兴趣的，或直接告诉我你想研究什么。"
        )
        reply = (
            "说明：以下内容基于学习端记录与通用技术概览，"
            "尚未执行正式检索；具体论文、实现细节和实验结论仍需在你确认后核验。\n\n"
            "(｡･ω･｡) 欢迎来到科研工作台！我是姜姜～\n\n"
            f"学习端记录显示你已学习：{learned}，当前进度记录为：{progress}。"
            "这些学习记录不代表已掌握或具备研究能力，实际理解与代码经验仍需确认。\n\n"
            f"{preview}\n\n"
            "你现在最想研究什么？"
        )
        return OrchestratorLlmOutcome(status="generated", reply_text=reply)


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    get_rate_limiter().reset()
    db_file = tmp_path / "test_direction_flow.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    from code_navi.research import router as research_router
    orig_orch = research_router._conversation_orchestrator
    research_router._conversation_orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeBridgeWelcomeGenerator()
    )

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        research_router._conversation_orchestrator = orig_orch
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()
        get_rate_limiter().reset()


def test_retry_last_regenerates_failed_bridge_welcome(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """桥接欢迎语失败后，重试本轮应当重新生成欢迎语，而不是 409 无可重试。"""
    from code_navi.research import router as research_router

    conversation_id = client.post("/api/v1/research/conversations", json={}).json()[
        "conversation_id"
    ]

    monkeypatch.setattr(
        research_router._conversation_orchestrator,
        "llm_generator",
        UnavailableWelcomeGenerator(),
    )
    put = client.put(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/learning-context",
        json={"learned_content": "图卷积网络 GCN", "learning_progress": "完成基础学习"},
    )
    assert put.status_code == 200
    state = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/state"
    ).json()
    assert state["last_status"] == "failed"

    monkeypatch.setattr(
        research_router._conversation_orchestrator,
        "llm_generator",
        FakeBridgeWelcomeGenerator(),
    )
    retried = client.post(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/messages/retry-last"
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "completed"

    conversation = client.get(f"/api/v1/research/conversations/{conversation_id}").json()
    bridge = [
        m["content"]
        for m in conversation["messages"]
        if m["role"] == "assistant" and "学习端记录显示你已学习" in m["content"]
    ]
    assert len(bridge) == 1

    state_after = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/state"
    ).json()
    assert state_after["last_status"] == "completed"
