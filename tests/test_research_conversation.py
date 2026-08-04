"""Offline behavior tests for conversational research clarification."""

from __future__ import annotations

import json
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
    RuntimeConversationDecisionGenerator,
    research_conversation_agent,
)
from code_navi.research.conversation_schemas import ResearchProfilePatch  # noqa: E402
from code_navi.research.router import _conversation_service  # noqa: E402
from code_navi.research.skill_runtime import (  # noqa: E402
    load_research_clarification_skill,
)
from code_navi.server import app  # noqa: E402
from kernel.core import ContentBlock, Message, ProviderResult  # noqa: E402
from kernel.providers import MockProvider  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    """Keep conversation tests isolated in the shared in-memory engine."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_generator() -> Generator[None, None, None]:
    original = _conversation_service.decision_generator
    yield
    _conversation_service.decision_generator = original


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


class FakeDecisionGenerator:
    """Deterministic application-level decision generator for API tests."""

    def __init__(self, outcomes: list[ConversationDecisionOutcome]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> ConversationDecisionOutcome:
        self.calls.append(kwargs)
        return self.outcomes.pop(0)


class FailingArtifactGenerator:
    """Prove that restoring a conversation must not wait for an LLM artefact call."""

    def generate(self, **kwargs: object) -> object:
        raise AssertionError("conversation restore must not generate LLM artefacts")


def _decision(**overrides: object) -> ResearchConversationDecision:
    values: dict[str, object] = {
        "reply": "我理解了你的初步想法，接下来优先确认研究目标。",
        "intent": "clarify",
        "profile_patch": {},
        "candidate_questions": [],
        "assumptions": [],
        "uncertainties": ["研究目标还不明确"],
        "next_question": "你更想比较效果、分析机制，还是探索应用场景？",
        "suggested_answers": ["比较效果", "分析机制", "探索应用场景"],
        "recommended_action": "continue_dialogue",
    }
    values.update(overrides)
    return ResearchConversationDecision.model_validate(values)


def test_new_conversation_is_not_a_fixed_five_field_questionnaire(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/research/conversations", json={})

    assert response.status_code == 201
    body = response.json()
    assert body["schema_version"] == "research-conversation.v1"
    assert body["stage"] == "exploring"
    assert body["ready_for_plan"] is False
    assert "completed" not in body
    assert body["messages"][-1]["role"] == "assistant"
    assert "missing_fields" not in body
    assert "next_question" in body
    assert "研究领域" not in body["next_question"]


def test_one_message_can_update_multiple_profile_dimensions(client: TestClient) -> None:
    fake = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(
                    profile_patch=ResearchProfilePatch(
                        topic="生成式 AI 辅助编程学习",
                        context="本科生编程课程",
                        constraints=["只能使用公开数据", "不训练模型"],
                    ),
                    candidate_questions=["不同提示策略是否影响编程解释的学习效果？"],
                    uncertainties=["尚未确定评价指标"],
                ),
                run_id="run-multi-field",
                event_count=4,
            )
        ]
    )
    _conversation_service.decision_generator = fake

    response = client.post(
        "/api/v1/research/conversations",
        json={
            "initial_message": (
                "我想研究生成式 AI 辅助编程学习，面向本科生，只能用公开数据，而且不想自己训练模型。"
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["profile"]["topic"] == "生成式 AI 辅助编程学习"
    assert body["profile"]["context"] == "本科生编程课程"
    assert body["profile"]["constraints"] == ["只能使用公开数据", "不训练模型"]
    assert body["candidate_questions"] == ["不同提示策略是否影响编程解释的学习效果？"]
    assert body["last_run_id"] == "run-multi-field"
    assert len(body["messages"]) == 2


def test_follow_up_can_correct_existing_profile_and_restore_without_model_call(
    client: TestClient,
) -> None:
    fake = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(profile_patch=ResearchProfilePatch(topic="教育人工智能")),
                run_id="run-1",
                event_count=3,
            ),
            ConversationDecisionOutcome.generated(
                _decision(
                    reply="已将主题收窄到编程学习场景。",
                    intent="correct",
                    profile_patch=ResearchProfilePatch(topic="生成式 AI 辅助编程学习"),
                ),
                run_id="run-2",
                event_count=3,
            ),
        ]
    )
    _conversation_service.decision_generator = fake
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究教育人工智能"},
    ).json()

    progressed = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "范围太大了，改成生成式 AI 辅助编程学习"},
    )
    restored = client.get(f"/api/v1/research/conversations/{created['conversation_id']}")

    assert progressed.status_code == 200
    assert progressed.json()["profile"]["topic"] == "生成式 AI 辅助编程学习"
    assert restored.status_code == 200
    assert restored.json()["profile"] == progressed.json()["profile"]
    assert len(restored.json()["messages"]) == 4
    assert len(fake.calls) == 2


def test_restore_does_not_generate_llm_artifacts(client: TestClient) -> None:
    """Restoring saved state must remain fast even when DeepSeek is configured."""
    original = _conversation_service.artifact_generator
    try:
        _conversation_service.artifact_generator = None
        created = client.post("/api/v1/research/conversations", json={}).json()
        _conversation_service.artifact_generator = FailingArtifactGenerator()

        restored = client.get(
            f"/api/v1/research/conversations/{created['conversation_id']}"
        )

        assert restored.status_code == 200
        assert restored.json()["conversation_id"] == created["conversation_id"]
    finally:
        _conversation_service.artifact_generator = original


def test_follow_up_can_explicitly_clear_rejected_candidate_questions(
    client: TestClient,
) -> None:
    fake = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(
                    profile_patch=ResearchProfilePatch(topic="教育人工智能"),
                    candidate_questions=["人工智能是否提升学习效果？"],
                ),
                run_id="run-candidate",
                event_count=3,
            ),
            ConversationDecisionOutcome.generated(
                _decision(
                    intent="correct",
                    profile_patch=ResearchProfilePatch(clear_fields=["candidate_questions"]),
                    candidate_questions=[],
                ),
                run_id="run-clear",
                event_count=3,
            ),
        ]
    )
    _conversation_service.decision_generator = fake
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究教育人工智能"},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "这个候选问题不合适，先清空"},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["candidate_questions"] == []


def test_invalid_model_output_falls_back_without_corrupting_profile(
    client: TestClient,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [ConversationDecisionOutcome.failed("invalid provider JSON")]
    )

    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我还不知道具体研究什么，可以先帮我分析吗？"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["generation_mode"] == "rules_fallback"
    assert body["profile"]["research_questions"] == []
    assert "不知道" not in json.dumps(body["profile"], ensure_ascii=False)
    assert body["next_question"]


def test_offline_fallback_keeps_known_topic_when_data_source_is_uncertain(
    client: TestClient,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [ConversationDecisionOutcome.unavailable()]
    )

    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究演化博弈法，数据来源不太清楚"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["generation_mode"] == "rules"
    assert body["profile"]["topic"] == "演化博弈法"
    assert body["profile"]["data_requirements"] is None
    assert any("数据" in item for item in body["profile"]["uncertainties"])


def test_offline_suggested_context_answer_advances_instead_of_repeating(
    client: TestClient,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.unavailable(),
            ConversationDecisionOutcome.unavailable(),
            ConversationDecisionOutcome.unavailable(),
        ]
    )
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究演化博弈"},
    ).json()
    narrowed = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "分析影响因素"},
    ).json()
    assert "哪类人群" in narrowed["next_question"]

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "真实课程或用户"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["context"] == "真实课程或用户"
    assert body["readiness"]["score"] > narrowed["readiness"]["score"]
    assert "哪类人群" not in body["next_question"]
    assert "哪些数据" in body["next_question"]


def test_offline_free_text_data_answer_advances_to_profile_review(
    client: TestClient,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.unavailable(),
            ConversationDecisionOutcome.unavailable(),
            ConversationDecisionOutcome.unavailable(),
            ConversationDecisionOutcome.unavailable(),
        ]
    )
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究演化博弈"},
    ).json()
    narrowed = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "解决实际问题"},
    ).json()
    assert "哪类人群" in narrowed["next_question"]
    contextualized = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "已有项目案例"},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "我只能使用公开数据集"},
    )

    assert response.status_code == 200
    body = response.json()
    assert contextualized["profile"]["context"] == "已有项目案例"
    assert body["profile"]["data_requirements"] == "我只能使用公开数据集"
    assert body["ready_for_plan"] is True
    assert "哪些数据" not in body["next_question"]


def test_offline_prepare_search_completes_skill_instead_of_repeating(
    client: TestClient,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [ConversationDecisionOutcome.unavailable()] * 5
    )
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究演化博弈"},
    ).json()
    focused = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "分析影响因素"},
    ).json()
    contextualized = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "真实课程或用户"},
    ).json()
    ready = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "只能使用公开材料"},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "准备探索性检索"},
    )

    assert focused["next_question"] != contextualized["next_question"]
    assert ready["ready_for_plan"] is True
    assert response.status_code == 200
    body = response.json()
    assert body["recommended_action"] == "prepare_search"
    assert body["next_skill"] == "academic-search"
    assert body["profile"]["topic"] == "演化博弈"
    assert body["next_question"] is None
    assert body["suggested_answers"] == []
    assert "需求确认 Skill 已完成" in body["reply"]


def test_offline_continue_narrowing_asks_a_new_profile_question(
    client: TestClient,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [ConversationDecisionOutcome.unavailable()] * 5
    )
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究演化博弈"},
    ).json()
    for message in ("分析影响因素", "真实课程或用户", "只能使用公开材料"):
        current = client.post(
            f"/api/v1/research/conversations/{created['conversation_id']}/messages",
            json={"message": message},
        ).json()
    assert "要继续收窄" in current["next_question"]

    body = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "继续收窄"},
    ).json()

    assert "要继续收窄" not in body["next_question"]
    assert "最终解释什么现象" in body["next_question"]
    assert body["recommended_action"] == "continue_dialogue"


def test_runtime_skill_contract_is_packaged_and_used_by_agent() -> None:
    skill = load_research_clarification_skill()

    assert "Never repeat the same question" in skill
    assert "academic-search" in skill
    assert research_conversation_agent.system_prompt == skill


def test_application_enforces_search_handoff_when_model_ignores_skill_transition(
    client: TestClient,
) -> None:
    repeated_question = "要继续收窄研究问题，还是准备探索性检索？"
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(
                    profile_patch=ResearchProfilePatch(
                        topic="演化博弈",
                        context="真实课程用户",
                        data_requirements="公开材料",
                    ),
                    candidate_questions=["哪些因素会影响演化博弈结果？"],
                    next_question=repeated_question,
                    suggested_answers=["继续收窄", "准备探索性检索"],
                ),
                run_id="run-ready",
                event_count=2,
            ),
            ConversationDecisionOutcome.generated(
                _decision(
                    reply="继续选择下一步。",
                    next_question=repeated_question,
                    suggested_answers=["继续收窄", "准备探索性检索"],
                ),
                run_id="run-ignored-transition",
                event_count=2,
            ),
        ]
    )
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究演化博弈"},
    ).json()

    body = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/messages",
        json={"message": "准备探索性检索"},
    ).json()

    assert body["generation_mode"] == "agent"
    assert body["recommended_action"] == "prepare_search"
    assert body["next_skill"] == "academic-search"
    assert body["next_question"] is None


def test_readiness_is_explainable_instead_of_a_required_field_gate(
    client: TestClient,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(
                    profile_patch=ResearchProfilePatch(
                        topic="RAG 回答可信度评测",
                        research_questions=["检索质量如何影响回答可信度？"],
                        context="高校课程知识库",
                        methods=["离线对照评测"],
                        constraints=["只使用公开材料"],
                    ),
                    recommended_action="review_profile",
                ),
                run_id="run-ready",
                event_count=3,
            )
        ]
    )

    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我已经有一个比较明确的研究设计"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["stage"] == "ready_for_plan"
    assert body["ready_for_plan"] is True
    assert body["readiness"]["score"] >= 70
    assert "missing_fields" not in body
    assert body["recommended_action"] == "review_profile"


def test_ready_conversation_returns_a_restorable_rules_research_plan(
    client: TestClient,
) -> None:
    """A plan is derived from the dynamic profile, not the legacy questionnaire."""
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(
                    profile_patch=ResearchProfilePatch(
                        topic="RAG 回答可信度评测",
                        research_questions=["检索质量如何影响回答可信度？"],
                        context="高校课程知识库",
                        methods=["离线对照评测"],
                        data_requirements="公开课程材料与检索日志",
                        constraints=["两周内完成最小验证"],
                        expected_output="研究简报与可复现评测原型",
                    ),
                    recommended_action="review_profile",
                ),
                run_id="run-plan",
                event_count=3,
            )
        ]
    )

    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想评测 RAG 回答的可信度"},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["ready_for_plan"] is True
    assert body["research_plan"]["schema_version"] == "research-plan.v1"
    assert body["research_plan"]["research_title"]["classification"] == "inference"
    assert body["research_plan"]["two_week_mvp_plan"]
    assert body["research_plan"]["suggested_search_keywords"]
    assert "论文事实" in body["research_plan"]["provenance_note"]
    assert body["research_mindmap"]["schema_version"] == "research-mindmap.v1"
    assert body["research_mindmap"]["root_node_id"] == "topic"
    assert any(
        node["id"] == "research-plan" and node["status"] == "inference"
        for node in body["research_mindmap"]["nodes"]
    )
    assert body["research_mindmap"]["edges"]

    restored = client.get(f"/api/v1/research/conversations/{body['conversation_id']}")

    assert restored.status_code == 200
    assert restored.json()["research_plan"] == body["research_plan"]
    assert restored.json()["research_mindmap"] == body["research_mindmap"]


def test_incomplete_conversation_has_no_research_plan(client: TestClient) -> None:
    response = client.post("/api/v1/research/conversations", json={})

    assert response.status_code == 201
    assert response.json()["research_plan"] is None


def test_code_draft_endpoint_requires_explicit_user_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/research/conversations/not-used/experiment-code-draft",
        json={"user_confirmed": False},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("profile_patch", "missing_label"),
    [
        (
            ResearchProfilePatch(
                motivation="提高课程知识库回答的可核验性",
                research_questions=["检索质量如何影响回答可信度？"],
                context="高校课程知识库",
                methods=["离线对照评测"],
                data_requirements="公开材料",
                evidence_preferences=["同行评审期刊"],
                time_scope="近三年",
                constraints=["两周内完成"],
                expected_output="研究简报",
            ),
            "研究主题",
        ),
        (
            ResearchProfilePatch(
                topic="RAG 回答可信度评测",
                motivation="提高课程知识库回答的可核验性",
                context="高校课程知识库",
                methods=["离线对照评测"],
                data_requirements="公开材料",
                evidence_preferences=["同行评审期刊"],
                time_scope="近三年",
                constraints=["两周内完成"],
                expected_output="研究简报",
            ),
            "研究问题",
        ),
    ],
)
def test_ready_plan_marks_missing_topic_or_question_for_verification(
    client: TestClient,
    profile_patch: ResearchProfilePatch,
    missing_label: str,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(profile_patch=profile_patch, recommended_action="review_profile"),
                run_id="run-partial-plan",
                event_count=2,
            )
        ]
    )

    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "请整理我已经明确的研究设想"},
    )

    assert response.status_code == 201
    plan = response.json()["research_plan"]
    assert plan["research_title"]["classification"] == "to_verify"
    assert missing_label in plan["research_title"]["content"]
    assert "None" not in plan["research_title"]["content"]


def test_ready_plan_safely_bounds_a_long_profile_question(client: TestClient) -> None:
    long_question = "问题" * 800
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(
                    profile_patch=ResearchProfilePatch(
                        topic="RAG 回答可信度评测",
                        research_questions=[long_question],
                        context="高校课程知识库",
                        methods=["离线对照评测"],
                        data_requirements="公开材料",
                    ),
                    recommended_action="review_profile",
                ),
                run_id="run-long-plan",
                event_count=2,
            )
        ]
    )

    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "请按这个很长的问题整理计划"},
    )

    assert response.status_code == 201
    plan = response.json()["research_plan"]
    assert len(plan["research_title"]["content"]) <= 1000
    assert all(len(keyword) <= 300 for keyword in plan["suggested_search_keywords"])


def test_runtime_generator_uses_agent_runtime_and_returns_auditable_run() -> None:
    decision = _decision(
        profile_patch=ResearchProfilePatch(topic="RAG 评测"),
        next_question="你更关注检索质量还是回答可信度？",
    )
    provider = MockProvider(
        [
            ProviderResult(
                Message(
                    "assistant",
                    (
                        ContentBlock(
                            "text",
                            {"text": decision.model_dump_json()},
                        ),
                    ),
                )
            )
        ]
    )
    generator = RuntimeConversationDecisionGenerator(
        provider_factory=lambda: provider,
        timeout_seconds=1,
    )

    outcome = generator.generate(
        profile={},
        messages=[],
        user_message="我想研究 RAG 评测",
        conversation_id="conversation-runtime-test",
    )

    assert outcome.status == "generated"
    assert outcome.decision is not None
    assert outcome.decision.profile_patch.topic == "RAG 评测"
    assert outcome.run_id
    assert outcome.event_count > 0
    assert provider.calls[0]["tools"] == []
    system_message = provider.calls[0]["messages"][0]
    assert system_message["metadata"]["agent_name"] == "research_conversation_agent"


def test_runtime_generator_rejects_blank_profile_patch_before_persistence() -> None:
    invalid_decision = _decision().model_dump(mode="json")
    invalid_decision["profile_patch"]["constraints"] = ["  "]
    provider = MockProvider(
        [
            ProviderResult(
                Message(
                    "assistant",
                    (ContentBlock("text", {"text": json.dumps(invalid_decision)}),),
                )
            )
        ]
    )
    generator = RuntimeConversationDecisionGenerator(
        provider_factory=lambda: provider,
        timeout_seconds=1,
    )

    outcome = generator.generate(
        profile={},
        messages=[],
        user_message="我有一个约束",
        conversation_id="conversation-invalid-patch",
    )

    assert outcome.status == "failed"
    assert outcome.decision is None


def test_missing_conversation_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/research/conversations/missing")

    assert response.status_code == 404
