"""Contracts for user-submitted experiment evidence and paper blueprints."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.research.conversation_agent import (  # noqa: E402
    ConversationDecisionOutcome,
    ResearchConversationDecision,
)
from code_navi.research.conversation_schemas import ResearchProfilePatch  # noqa: E402
from code_navi.research.router import _conversation_service  # noqa: E402
from code_navi.server import app  # noqa: E402
from research_llm_fakes import ContextAwareArtifactGenerator  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_generator() -> Generator[None, None, None]:
    original = _conversation_service.decision_generator
    original_artifact = _conversation_service.artifact_generator
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    yield
    _conversation_service.decision_generator = original
    _conversation_service.artifact_generator = original_artifact


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


class ReadyDecisionGenerator:
    def generate(self, **_: object) -> ConversationDecisionOutcome:
        return ConversationDecisionOutcome.generated(
            ResearchConversationDecision(
                reply="研究画像已整理，可生成规则研究计划。",
                intent="clarify",
                profile_patch=ResearchProfilePatch(
                    topic="生成式 AI 编程学习反馈",
                    motivation="改进本科生反馈体验",
                    research_questions=["即时反馈是否改善 Python 练习表现？"],
                    context="30 名本科生 Python 课程",
                    methods=["小规模对照研究"],
                    data_requirements="匿名学习记录",
                    constraints=["两周内完成", "没有 GPU"],
                    expected_output="课程项目报告",
                ),
                candidate_questions=["即时反馈是否改善 Python 练习表现？"],
                assumptions=[],
                uncertainties=["样本量与伦理许可待确认"],
                next_question="是否准备查看研究计划？",
                suggested_answers=["查看计划", "补充约束", "继续讨论"],
                recommended_action="review_profile",
            ),
            run_id="test-ready",
            event_count=1,
        )


def _ready_conversation(client: TestClient) -> str:
    """Create a ready conversation and generate its plan explicitly.

    Plans are model-generated on user request (checkpoint 3 contract); a new
    conversation no longer ships a rules plan by default, so the fixture calls
    the dedicated endpoint with the faked artifact generator.
    """
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    response = client.post(
        "/api/v1/research/conversations", json={"initial_message": "我想研究编程反馈"}
    )
    assert response.status_code == 201
    conversation_id = response.json()["conversation_id"]
    plan_response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/research-plan",
        json={"user_confirmed": True},
    )
    assert plan_response.status_code == 200
    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert restored.status_code == 200
    assert restored.json()["research_plan"] is not None
    return conversation_id


def _submission() -> dict[str, object]:
    return {
        "experiment_name": "即时反馈小样本对照",
        "goal": "比较两种反馈时机的练习完成率",
        "items": [
            {
                "category": "data_or_sample",
                "content": "实际纳入 30 名学生的匿名练习记录。",
                "classification": "fact",
            },
            {
                "category": "metric_or_result",
                "content": "即时反馈组完成率 0.73，对照组完成率 0.61。",
                "classification": "fact",
                "related_plan_item": "两周最小可行验证计划",
            },
            {
                "category": "failure_or_limitation",
                "content": "随机分组尚未完成，不能解释因果。",
                "classification": "to_verify",
            },
        ],
    }


def test_user_experiment_evidence_persists_and_restores_free_text(client: TestClient) -> None:
    conversation_id = _ready_conversation(client)

    saved = client.post(
        f"/api/v1/research/conversations/{conversation_id}/experiment-evidence-bundles",
        json=_submission(),
    )
    restored = client.get(
        f"/api/v1/research/conversations/{conversation_id}/experiment-evidence-bundles"
    )

    assert saved.status_code == 201
    body = saved.json()
    assert body["schema_version"] == "experiment-evidence.v1"
    assert body["items"][0]["basis"].startswith("用户于")
    assert body["items"][0]["source_scope"] == "user_submitted_text"
    assert restored.status_code == 200
    assert restored.json()[0]["items"][1]["content"] == "即时反馈组完成率 0.73，对照组完成率 0.61。"


def test_blueprint_without_experiment_evidence_is_explicitly_pending(client: TestClient) -> None:
    conversation_id = _ready_conversation(client)

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-blueprint",
        json={"user_confirmed": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["generation_mode"] == "llm"
    assert body["submission_readiness"]["classification"] == "to_verify"
    experiment = next(item for item in body["sections"] if item["section"] == "实验")
    assert experiment["evidence_references"] == []
    assert experiment["missing_evidence"]


def test_blueprint_traces_experiment_facts_and_never_invents_them(client: TestClient) -> None:
    conversation_id = _ready_conversation(client)
    saved = client.post(
        f"/api/v1/research/conversations/{conversation_id}/experiment-evidence-bundles",
        json=_submission(),
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-blueprint",
        json={"user_confirmed": True},
    )

    assert response.status_code == 200
    experiment = next(item for item in response.json()["sections"] if item["section"] == "实验")
    assert any(
        reference["bundle_id"] == saved["bundle_id"]
        for reference in experiment["evidence_references"]
    )
    assert all(
        reference["classification"] == "fact" for reference in experiment["evidence_references"]
    )
    assert "实验结果显著" not in "\n".join(
        reference["label"] for reference in experiment["evidence_references"]
    )


def test_creating_evidence_and_blueprint_never_triggers_academic_search(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation_id = _ready_conversation(client)
    monkeypatch.setattr(
        "code_navi.research.conversation_search_service.ResearchConversationSearchService.search",
        lambda *_args, **_kwargs: pytest.fail("实验结果录入或蓝图生成不应发起联网检索"),
    )

    assert (
        client.post(
            f"/api/v1/research/conversations/{conversation_id}/experiment-evidence-bundles",
            json=_submission(),
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/research/conversations/{conversation_id}/paper-blueprint",
            json={"user_confirmed": True},
        ).status_code
        == 200
    )
