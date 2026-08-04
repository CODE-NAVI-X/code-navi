"""Integration tests for guarded LLM research clarification guidance."""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, engine  # noqa: E402
from code_navi.research.llm import (  # noqa: E402
    GuidanceOutcome,
    LlmGuidance,
    ProviderGuidanceGenerator,
)
from code_navi.research.router import _service  # noqa: E402
from code_navi.research.rules import next_question  # noqa: E402
from code_navi.research.schemas import ResearchState  # noqa: E402
from code_navi.server import app  # noqa: E402
from kernel.core import ContentBlock, Message  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    """Keep API tests isolated while reusing the in-memory SQLite engine."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


class FakeGuidanceGenerator:
    def __init__(self, outcome: GuidanceOutcome) -> None:
        self.outcome = outcome
        self.calls = 0
        self.call_arguments: list[dict[str, object]] = []

    def generate(self, **_kwargs: object) -> GuidanceOutcome:
        self.calls += 1
        self.call_arguments.append(_kwargs)
        return self.outcome


@pytest.fixture(autouse=True)
def restore_service_generator() -> Generator[None, None, None]:
    original = _service.guidance_generator
    yield
    _service.guidance_generator = original


def _create(client: TestClient) -> str:
    return client.post("/api/v1/research/sessions", json={}).json()["session_id"]


def test_configured_generator_returns_validated_personalized_guidance(client: TestClient) -> None:
    fake = FakeGuidanceGenerator(
        GuidanceOutcome.generated(
            LlmGuidance(
                reply="你已明确研究领域，接下来把目标收窄到一个可比较的问题。",
                next_question="在这个方向中，你最想比较哪一种学习反馈效果？",
                options=["比较两种反馈策略", "评估准确性变化", "分析使用体验"],
            )
        )
    )
    _service.guidance_generator = fake
    session_id = _create(client)

    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    ).json()

    assert body["generation_mode"] == "llm"
    assert body["reply"] == "你已明确研究领域，接下来把目标收窄到一个可比较的问题。"
    assert body["next_question"]["field"] == "core_question"
    assert body["next_question"]["options"] == [
        "比较两种反馈策略",
        "评估准确性变化",
        "分析使用体验",
    ]
    assert fake.calls == 1


def test_provider_generator_uses_existing_openai_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProvider:
        def complete(self, _messages: object) -> SimpleNamespace:
            return SimpleNamespace(
                message=Message(
                    "assistant",
                    (
                        ContentBlock(
                            "text",
                            {
                                "text": (
                                    '{"reply":"已记录研究领域。",'
                                    '"next_question":"请明确核心问题。",'
                                    '"options":["比较方案 A", "比较方案 B", "评估体验"],'
                                    '"suggested_value":null}'
                                )
                            },
                        ),
                    ),
                )
            )

    monkeypatch.setenv("CODE_NAVI_PROVIDER", "openai")
    monkeypatch.setenv("CODE_NAVI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("code_navi.research.llm.create_provider", lambda _settings: FakeProvider())
    question = next_question(ResearchState())
    assert question is not None

    outcome = ProviderGuidanceGenerator().generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=question,
        requesting_suggestion=False,
    )

    assert outcome.status == "generated"
    assert outcome.guidance is not None
    assert outcome.guidance.options == ["比较方案 A", "比较方案 B", "评估体验"]


def test_provider_generator_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProvider:
        def complete(self, _messages: object) -> SimpleNamespace:
            return SimpleNamespace(
                message=Message("assistant", (ContentBlock("text", {"text": "not a JSON object"}),))
            )

    monkeypatch.setenv("CODE_NAVI_PROVIDER", "openai")
    monkeypatch.setenv("CODE_NAVI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("code_navi.research.llm.create_provider", lambda _settings: FakeProvider())
    question = next_question(ResearchState())
    assert question is not None

    outcome = ProviderGuidanceGenerator().generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=question,
        requesting_suggestion=False,
    )

    assert outcome.status == "failed"


def test_provider_generator_timeout_becomes_a_safe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowProvider:
        def complete(self, _messages: object) -> SimpleNamespace:
            time.sleep(0.1)
            return SimpleNamespace(message=Message("assistant", ()))

    monkeypatch.setenv("CODE_NAVI_PROVIDER", "openai")
    monkeypatch.setenv("CODE_NAVI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("code_navi.research.llm.create_provider", lambda _settings: SlowProvider())
    question = next_question(ResearchState())
    assert question is not None

    outcome = ProviderGuidanceGenerator(timeout_seconds=0.001).generate(
        state=ResearchState(),
        user_reply="教育场景中的人工智能",
        target_question=question,
        requesting_suggestion=False,
    )

    assert outcome.status == "failed"
    assert outcome.reason == "research guidance provider timed out"


def test_generator_failure_falls_back_to_fixed_question_and_options(client: TestClient) -> None:
    _service.guidance_generator = FakeGuidanceGenerator(GuidanceOutcome.failed("timeout"))
    session_id = _create(client)

    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    ).json()

    assert body["generation_mode"] == "rules_fallback"
    assert body["next_question"]["question"] == "你希望重点解决或验证什么问题？"
    assert len(body["next_question"]["options"]) == 3

    restored = client.get(f"/api/v1/research/sessions/{session_id}")
    assert restored.status_code == 200
    assert restored.json()["generation_mode"] == "rules_fallback"


def test_recommendation_request_uses_suggested_value_instead_of_uncertainty(
    client: TestClient,
) -> None:
    fake = FakeGuidanceGenerator(
        GuidanceOutcome.generated(
            LlmGuidance(
                reply="建议先从公开数据集上的两种反馈策略比较开始。",
                next_question="你计划使用什么数据、对象或研究方法？",
                options=["公开数据集与实验评测", "课堂问卷与访谈", "原型系统案例分析"],
                suggested_value="比较两种教学反馈策略的学习效果",
            )
        )
    )
    _service.guidance_generator = fake
    session_id = _create(client)
    client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    )

    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "我不知道，有什么推荐吗"},
    ).json()

    assert body["state"]["core_question"] == "比较两种教学反馈策略的学习效果"
    assert body["state"]["core_question"] != "我不知道，有什么推荐吗"
    assert body["turns"][-1]["input_mode"] == "llm_suggested"
    assert fake.call_arguments[-1]["suggestion_question"].field == "core_question"  # type: ignore[union-attr]
    assert fake.call_arguments[-1]["target_question"].field == "data_and_method"  # type: ignore[union-attr]


def test_model_echo_of_uncertainty_is_rejected(client: TestClient) -> None:
    _service.guidance_generator = FakeGuidanceGenerator(
        GuidanceOutcome.generated(
            LlmGuidance(
                reply="我无法给出具体建议。",
                next_question="请说明核心问题。",
                options=["方案 A", "方案 B", "方案 C"],
                suggested_value="我不知道，有什么推荐吗",
            )
        )
    )
    session_id = _create(client)
    client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    )

    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "我不知道，有什么推荐吗"},
    ).json()

    assert body["generation_mode"] == "rules_fallback"
    assert body["state"]["core_question"] is None
    assert len(body["turns"]) == 1

    restored = client.get(f"/api/v1/research/sessions/{session_id}")
    assert restored.status_code == 200
    assert restored.json()["generation_mode"] == "rules_fallback"


def test_recommendation_request_for_final_field_still_calls_generator(client: TestClient) -> None:
    _service.guidance_generator = FakeGuidanceGenerator(GuidanceOutcome.unavailable())
    session_id = _create(client)
    for answer in ("教育技术", "比较反馈策略", "公开数据集评测", "两周内完成"):
        response = client.post(
            f"/api/v1/research/sessions/{session_id}/turns",
            json={"answer": answer},
        )
        assert response.status_code == 200

    fake = FakeGuidanceGenerator(
        GuidanceOutcome.generated(
            LlmGuidance(
                reply="建议先交付可复现的实验报告。",
                next_question="研究信息已完整。",
                options=["查看简报", "查看计划", "新建会话"],
                suggested_value="一份可复现实验报告和演示原型",
            )
        )
    )
    _service.guidance_generator = fake
    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "我不知道，有什么推荐吗"},
    ).json()

    assert body["completed"] is True
    assert body["state"]["expected_deliverable"] == "一份可复现实验报告和演示原型"
    assert fake.calls == 1
    assert fake.call_arguments[0]["suggestion_question"].field == "expected_deliverable"  # type: ignore[union-attr]
    assert fake.call_arguments[0]["target_question"] is None


def test_unavailable_generator_keeps_rules_flow(client: TestClient) -> None:
    _service.guidance_generator = FakeGuidanceGenerator(GuidanceOutcome.unavailable())
    session_id = _create(client)

    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    ).json()

    assert body["generation_mode"] == "rules"
    assert body["next_question"]["field"] == "core_question"


def test_uncertainty_without_a_model_does_not_become_research_data(client: TestClient) -> None:
    _service.guidance_generator = FakeGuidanceGenerator(GuidanceOutcome.unavailable())
    session_id = _create(client)
    client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    )

    body = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "我不知道，有什么推荐吗"},
    ).json()

    assert body["generation_mode"] == "rules"
    assert body["state"]["core_question"] is None
    assert body["next_question"]["field"] == "core_question"
    assert body["turns"][-1]["value"] == "教育场景中的人工智能"


def test_session_restore_never_invokes_generator(client: TestClient) -> None:
    fake = FakeGuidanceGenerator(GuidanceOutcome.unavailable())
    _service.guidance_generator = fake
    session_id = _create(client)

    response = client.get(f"/api/v1/research/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["generation_mode"] == "rules"
    assert fake.calls == 0


def test_session_restore_keeps_validated_personalized_guidance(client: TestClient) -> None:
    fake = FakeGuidanceGenerator(
        GuidanceOutcome.generated(
            LlmGuidance(
                reply="现在把问题收窄到可比较的目标。",
                next_question="你想比较哪一种反馈策略？",
                options=["即时反馈", "延迟反馈", "混合反馈"],
            )
        )
    )
    _service.guidance_generator = fake
    session_id = _create(client)
    client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "教育场景中的人工智能"},
    )

    response = client.get(f"/api/v1/research/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["generation_mode"] == "llm"
    assert response.json()["next_question"]["options"] == ["即时反馈", "延迟反馈", "混合反馈"]
    assert fake.calls == 1
