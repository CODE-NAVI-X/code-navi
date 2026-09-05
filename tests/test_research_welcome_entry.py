"""Entry welcome contract: direct entry and learning handoff use the new bridge welcome.

Covers the redesign requirement that neither the legacy five-step opening nor the
legacy learning-background summary is generated anymore:
- direct `/research` entry (new conversation) opens with the new empty-state welcome;
- the first valid learning-context PUT triggers one idempotent `welcome_and_bridge`
  turn that objectively quotes the learning records and shows 5 dynamic cards;
- provider failures stay explicitly failed instead of faking a template reply.
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
from code_navi.server import app

LEGACY_FLOW_MARKERS = (
    "描述想法",
    "整理科研画像",
    "主动检索与记录",
    "学习背景开场总结",
    "先不用按表格回答",
)

SCOPE_PREFIX = (
    "说明：以下内容基于学习端记录与通用技术概览，"
    "尚未执行正式检索；具体论文、实现细节和实验结论仍需在你确认后核验。"
)

WELCOME_OPENING = (
    "(｡･ω･｡) 欢迎来到科研工作台！我是姜姜～\n\n"
    "这里不是一上来就让你填表或做实验，而是陪你把“我想做什么研究”慢慢聊清楚："
    "从选方向、补前置知识，到设计实验、看结果，我们一步一步来。\n\n"
    "学习端记录会作为方向建议的来源，但不代表已经掌握相关知识、具备实验能力或能够完成复现。\n\n"
    "我会先根据学习内容准备几个可探索方向。你可以选一个感兴趣的，"
    "也可以直接告诉我：你现在最想研究什么？"
)

EMPTY_WELCOME_REPLY = f"{SCOPE_PREFIX}\n\n{WELCOME_OPENING}"


class FakeBridgeWelcomeGenerator:
    """Render the contract-shaped welcome reply from the assembled prompt."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation_history=(),
        conversation_id: str = "",
        **kwargs,
    ) -> OrchestratorLlmOutcome:
        learned = self._prompt_field(user_prompt, "已学内容")
        progress = self._prompt_field(user_prompt, "学习进度")
        has_learning_input = bool(
            learned not in (None, "暂无学习端输入（空态）")
            or progress not in (None, "暂无学习进度")
        )
        if not has_learning_input:
            return OrchestratorLlmOutcome(status="generated", reply_text=EMPTY_WELCOME_REPLY)
        cards = generate_dynamic_direction_cards(learned, progress)
        card_lines = "\n".join(
            f"{index}. 【{card.title}】：{card.description}"
            for index, card in enumerate(cards, start=1)
        )
        reply = (
            f"{SCOPE_PREFIX}\n\n{WELCOME_OPENING}\n\n"
            f"学习端记录显示你已学习：{learned}，当前进度记录为：{progress}。"
            "这些学习记录不代表已掌握或具备研究能力，实际理解与代码经验仍需确认。\n\n"
            f"可以探索的方向包括：\n{card_lines}"
        )
        return OrchestratorLlmOutcome(status="generated", reply_text=reply)

    @staticmethod
    def _prompt_field(user_prompt: str, name: str) -> str | None:
        match = re.search(rf"{name}：(.+)", user_prompt)
        return match.group(1).strip() if match else None


class UnavailableWelcomeGenerator:
    """Simulate a provider that never answers (unavailable), like CI without keys."""

    def generate(self, **_kwargs) -> OrchestratorLlmOutcome:
        return OrchestratorLlmOutcome(status="unavailable", reason="Provider not configured")


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    get_rate_limiter().reset()
    db_file = tmp_path / "test_welcome_entry.db"
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


def _bridge_welcome_texts(messages: list[dict]) -> list[str]:
    return [
        message["content"]
        for message in messages
        if message["role"] == "assistant" and "学习端记录显示你已学习" in message["content"]
    ]


def test_new_conversation_opens_with_new_empty_state_welcome(client: TestClient) -> None:
    """直接新建科研会话：新版空态欢迎，无旧五步，不伪造方向卡，阶段 research_need。"""
    created = client.post("/api/v1/research/conversations", json={})
    assert created.status_code == 201
    data = created.json()
    conversation_id = data["conversation_id"]

    assistant_messages = [m for m in data["messages"] if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    content = assistant_messages[0]["content"]
    assert "欢迎来到科研工作台！我是姜姜" in content
    assert "你现在最想研究什么" in content
    for marker in LEGACY_FLOW_MARKERS:
        assert marker not in content

    cards = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/direction-cards"
    ).json()["cards"]
    assert cards == []

    state = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/state"
    ).json()
    assert state["current_stage"] == "research_need"
    assert state["completed_stages"] == []


def test_learning_put_triggers_bridge_welcome_with_records_and_cards(
    client: TestClient,
) -> None:
    """首次 PUT 有效学习输入：桥接欢迎语客观引用记录并给出 5 张动态方向卡。"""
    conversation_id = client.post("/api/v1/research/conversations", json={}).json()[
        "conversation_id"
    ]
    put = client.put(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/learning-context",
        json={"learned_content": "图卷积网络 GCN", "learning_progress": "完成基础学习"},
    )
    assert put.status_code == 200
    assert put.json()["learned_content"] == "图卷积网络 GCN"

    conversation = client.get(f"/api/v1/research/conversations/{conversation_id}").json()
    bridge_texts = _bridge_welcome_texts(conversation["messages"])
    assert bridge_texts, "first valid learning PUT must trigger the bridge welcome"
    content = bridge_texts[-1]
    assert "学习端记录显示你已学习：图卷积网络 GCN" in content
    assert "当前进度记录为：完成基础学习" in content
    assert "这些学习记录不代表已掌握或具备研究能力" in content

    cards = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/direction-cards"
    ).json()["cards"]
    assert len(cards) == 5
    assert all("图" in card["title"] or "gcn" in card["title"].lower() for card in cards)
    assert cards[0]["title"] in content

    state = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/state"
    ).json()
    assert state["current_stage"] == "research_need"
    assert state["subtasks"]["need_defined"] is False


def test_learning_entry_screen_has_no_legacy_flow_text(client: TestClient) -> None:
    """学习端进入后的首屏消息不得出现旧五步/旧学习总结文本。"""
    conversation_id = client.post("/api/v1/research/conversations", json={}).json()[
        "conversation_id"
    ]
    put = client.put(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/learning-context",
        json={"learned_content": "图卷积网络 GCN", "learning_progress": "完成基础学习"},
    )
    assert put.status_code == 200

    conversation = client.get(f"/api/v1/research/conversations/{conversation_id}").json()
    all_text = "\n".join(message["content"] for message in conversation["messages"])
    for marker in LEGACY_FLOW_MARKERS:
        assert marker not in all_text


def test_repeated_put_and_restore_do_not_duplicate_bridge_welcome(
    client: TestClient,
) -> None:
    """重复 PUT 同一学习输入、重复读取会话，都不得再插入第二条桥接欢迎语。"""
    conversation_id = client.post("/api/v1/research/conversations", json={}).json()[
        "conversation_id"
    ]
    payload = {"learned_content": "图卷积网络 GCN", "learning_progress": "完成基础学习"}
    assert client.put(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/learning-context",
        json=payload,
    ).status_code == 200
    assert client.put(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/learning-context",
        json=payload,
    ).status_code == 200

    first = client.get(f"/api/v1/research/conversations/{conversation_id}").json()
    assert len(_bridge_welcome_texts(first["messages"])) == 1

    restored = client.get(f"/api/v1/research/conversations/{conversation_id}").json()
    assert len(_bridge_welcome_texts(restored["messages"])) == 1


def test_provider_failure_keeps_welcome_explicitly_failed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider 失败：显式 failed，不插入模板伪装成功，不推进阶段、不建画像版本。"""
    from code_navi.research import router as research_router

    monkeypatch.setattr(
        research_router._conversation_orchestrator,
        "llm_generator",
        UnavailableWelcomeGenerator(),
    )

    conversation_id = client.post("/api/v1/research/conversations", json={}).json()[
        "conversation_id"
    ]
    put = client.put(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/learning-context",
        json={"learned_content": "图卷积网络 GCN", "learning_progress": "完成基础学习"},
    )
    # PUT 契约不变：存储成功即 200，欢迎语失败只体现在会话状态里。
    assert put.status_code == 200
    assert put.json()["learned_content"] == "图卷积网络 GCN"

    state = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/state"
    ).json()
    assert state["last_status"] == "failed"
    assert state["last_error"]
    assert state["current_stage"] == "research_need"
    assert state["subtasks"]["need_defined"] is False

    conversation = client.get(f"/api/v1/research/conversations/{conversation_id}").json()
    assistant_texts = [
        message["content"] for message in conversation["messages"] if message["role"] == "assistant"
    ]
    assert len(assistant_texts) == 1  # 只有新建会话的空态欢迎，没有伪装成功的桥接
    assert all("学习端记录显示你已学习" not in text for text in assistant_texts)

    profiles = client.get(
        f"/api/v1/research/conversations/{conversation_id}/orchestrator/learner-profiles"
    ).json()
    assert profiles["current_profile"] is None
