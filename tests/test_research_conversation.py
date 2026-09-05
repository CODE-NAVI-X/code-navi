"""Offline behavior tests for conversational research clarification."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.context_transfer.schemas import (  # noqa: E402
    ConfirmedContextProvenance,
    ContextSourceObject,
    SelectedContextContent,
)
from code_navi.db import SessionLocal, engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.research.conversation_agent import (  # noqa: E402
    ConversationDecisionOutcome,
    ResearchConversationDecision,
    RuntimeConversationDecisionGenerator,
    build_research_conversation_input,
    research_conversation_agent,
)
from code_navi.research.conversation_context import (  # noqa: E402
    ConversationCompactor,
    ResearchContextAssembler,
    ResearchContextInput,
)
from code_navi.research.conversation_schemas import (  # noqa: E402
    CreateResearchConversationRequest,
    ResearchContextSummary,
    ResearchConversationMessage,
    ResearchProfile,
    ResearchProfilePatch,
    SendResearchMessageRequest,
)
from code_navi.research.conversation_service import (  # noqa: E402
    ResearchConversationService,
    assess_readiness,
)
from code_navi.research.models import ResearchConversationModel  # noqa: E402
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome  # noqa: E402
from code_navi.research.router import _conversation_service  # noqa: E402
from code_navi.research.skill_runtime import (  # noqa: E402
    load_research_clarification_skill,
)
from code_navi.server import app  # noqa: E402
from kernel.core import ContentBlock, Message, ProviderResult  # noqa: E402
from kernel.providers import MockProvider  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Keep conversation tests isolated in the shared in-memory engine and mock provider."""
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_generator() -> Generator[None, None, None]:
    original_decision = _conversation_service.decision_generator
    original_artifact = _conversation_service.artifact_generator
    yield
    _conversation_service.decision_generator = original_decision
    _conversation_service.artifact_generator = original_artifact


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


class StaticArtifactGenerator:
    def __init__(self, outcome: ArtifactLlmOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> ArtifactLlmOutcome:
        self.calls.append(kwargs)
        return self.outcome


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
    assert "confirmed_learning_context" in skill
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


@pytest.mark.parametrize(
    "message",
    [
        (
            "我想研究图卷积网络在 Cora 节点分类中的表现：候选问题是 GCN 与 GraphSAGE 的 "
            "Accuracy 差异；方法采用对照实验；使用 Cora 数据集，指标为 Accuracy；我只有 RTX "
            "4060 笔记本，计划两周完成，产出开题报告。"
        ),
        (
            "拟以生成式 AI 辅助本科编程学习为题，研究问题是不同提示策略如何影响学习成绩；"
            "采用离线对照评测，数据为公开课程记录，指标包括正确率；资源限制是单张消费级 "
            "GPU，时间安排为三周，交付研究计划。"
        ),
        (
            "课题聚焦医疗文本分类的可解释性，想回答注意力可视化是否改善医生理解；通过案例 "
            "比较分析 MIMIC 公开样本，以 F1 为指标；仅可使用 16GB 内存设备，一个月内完成 "
            "文献综述。"
        ),
        (
            "计划比较联邦学习与集中训练在校园传感器预测中的效果：研究问题为隐私约束下误差 "
            "是否扩大；方法是模拟实验，数据集为 UCI 公开数据，指标 RMSE；没有服务器，"
            "两周内给出原型系统。"
        ),
        (
            "希望评估检索增强生成在课程问答中的可信度，候选问题是检索覆盖率如何影响答案 "
            "准确率；使用日志分析和人工标注，数据为公开问答集，指标为 Accuracy 与覆盖率；"
            "资源是本地笔记本，计划四周完成论文。"
        ),
    ],
)
def test_rules_fallback_accepts_complete_research_request_in_one_turn(
    client: TestClient,
    message: str,
) -> None:
    _conversation_service.decision_generator = FakeDecisionGenerator(
        [ConversationDecisionOutcome.unavailable()]
    )

    response = client.post("/api/v1/research/conversations", json={"initial_message": message})

    assert response.status_code == 201
    body = response.json()
    assert body["generation_mode"] == "rules"
    assert body["profile"]["topic"]
    assert body["profile"]["research_questions"]
    assert body["profile"]["methods"]
    assert body["profile"]["data_requirements"]
    assert body["profile"]["metrics"]
    assert body["profile"]["constraints"]
    assert body["profile"]["time_scope"]
    assert body["stage"] == "ready_for_plan"
    assert body["ready_for_plan"] is True
    assert body["readiness"]["can_prepare_search"] is True
    assert "研究主题" not in (body["next_question"] or "")
    assert "研究问题" not in (body["next_question"] or "")


def test_search_readiness_does_not_diverge_from_plan_stage() -> None:
    readiness = assess_readiness(
        ResearchProfile(topic="图卷积网络", research_questions=["GCN 是否优于基线？"])
    )

    assert readiness.stage != "ready_for_plan"
    assert readiness.can_prepare_search is False


def test_search_readiness_does_not_require_legacy_context_field() -> None:
    readiness = assess_readiness(
        ResearchProfile(
            topic="图卷积网络",
            research_questions=["GCN 是否优于基线？"],
            motivation="在小规模环境中复现经典模型。",
            methods=["两层 GCN"],
            data_requirements="Cora 数据集",
            constraints=["个人电脑"],
            time_scope="两周",
        )
    )

    assert readiness.can_prepare_search is True
    assert "研究对象或应用场景仍不清楚" not in readiness.reasons


def test_search_readiness_score_is_bounded_for_complete_profile() -> None:
    readiness = assess_readiness(
        ResearchProfile(
            topic="图卷积网络",
            motivation="复现经典模型并比较基线。",
            research_questions=["GCN 是否优于基线？"],
            context="个人电脑上的 Cora 节点分类",
            methods=["两层 GCN", "MLP 基线"],
            data_requirements="Cora 数据集",
            metrics=["Accuracy"],
            constraints=["单卡运行"],
            time_scope="两周",
            expected_output="实验记录与研究简报",
            evidence_preferences=["原始论文"],
        )
    )

    assert readiness.score == 100
    assert readiness.can_prepare_search is True


def test_ready_conversation_does_not_return_unrequested_rule_research_plan(
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
    assert body["research_plan"] is None
    assert body["research_mindmap"] is None

    restored = client.get(f"/api/v1/research/conversations/{body['conversation_id']}")

    assert restored.status_code == 200
    assert restored.json()["research_plan"] is None
    assert restored.json()["research_mindmap"] is None


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


def test_conversation_response_does_not_generate_optional_artifacts(
    client: TestClient,
) -> None:
    _conversation_service.artifact_generator = FailingArtifactGenerator()

    response = client.post("/api/v1/research/conversations", json={})

    assert response.status_code == 201
    assert response.json()["topic_difficulty_analysis"] is None
    assert response.json()["experiment_design"] is None


def test_difficulty_personalization_requires_explicit_endpoint(
    client: TestClient,
) -> None:
    generator = StaticArtifactGenerator(
        ArtifactLlmOutcome.generated(
            '{"title":"个性化难点","information_scope":"profile_and_plan_only",'
            '"core_judgment":"当前画像尚不完整，需要先收窄研究问题。",'
            '"items":[{"area":"问题边界","content":"需要先收窄问题。",'
            '"classification":"to_verify","basis":"当前画像尚不完整。",'
            '"source_scope":"profile_and_plan_only",'
            '"relevance":"问题边界决定检索与实验范围。",'
            '"suggested_action":"先补充一个可比较的研究问题。"}],'
            '"next_action":"补充研究问题后生成研究计划。",'
            '"provenance_note":"用户显式触发的个性化建议。"}',
            run_id="run-artifact",
            event_count=3,
        )
    )
    _conversation_service.artifact_generator = generator
    created = client.post("/api/v1/research/conversations", json={}).json()

    rejected = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/topic-difficulty-analysis",
        json={"user_confirmed": False},
    )
    generated = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/topic-difficulty-analysis",
        json={"user_confirmed": True},
    )

    assert rejected.status_code == 422
    assert generated.status_code == 200
    assert generated.json()["generation_mode"] == "llm"
    assert generated.json()["run_id"] == "run-artifact"
    assert len(generator.calls) == 1


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
def test_ready_conversation_does_not_render_plan_without_llm_generation(
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
    assert response.json()["research_plan"] is None


def test_ready_conversation_does_not_render_rule_plan_for_long_profile(client: TestClient) -> None:
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
    assert response.json()["research_plan"] is None


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
    confirmed_context = ConfirmedContextProvenance(
        transfer_id="transfer-runtime-test",
        source_module="learning",
        source_object=ContextSourceObject(type="notebook_item", id="note-runtime-test"),
        source_scope_id="sess-runtime-test",
        target_module="research",
        topic="RAG 评测",
        summary="已确认的学习背景",
        selected_content=[
            SelectedContextContent(
                kind="summary",
                label="学习重点",
                content="检索质量影响证据覆盖。",
            )
        ],
        confirmed_at=datetime.now(UTC),
    )

    outcome = generator.generate(
        profile={},
        conversation_history=(),
        user_message="我想研究 RAG 评测",
        conversation_id="conversation-runtime-test",
        confirmed_context=confirmed_context,
    )

    assert outcome.status == "generated"
    assert outcome.decision is not None
    assert outcome.decision.profile_patch.topic == "RAG 评测"
    assert outcome.run_id
    assert outcome.event_count > 0
    assert provider.calls[0]["tools"] == []
    system_message = provider.calls[0]["messages"][0]
    assert system_message["metadata"]["agent_name"] == "research_conversation_agent"
    runtime_payload = json.loads(provider.calls[0]["messages"][1]["content"][0]["text"])
    assert "recent_messages" not in runtime_payload
    assert runtime_payload["confirmed_learning_context"]["topic"] == "RAG 评测"
    assert runtime_payload["confirmed_learning_context"]["selected_content"] == [
        {
            "kind": "summary",
            "label": "学习重点",
            "content": "检索质量影响证据覆盖。",
        }
    ]


def test_rebuilt_service_restores_explicit_history_and_keeps_conversations_isolated() -> None:
    decisions = [
        _decision(reply="第一轮回复", profile_patch=ResearchProfilePatch(topic="会话甲")),
        _decision(reply="第二轮回复"),
        _decision(reply="独立回复", profile_patch=ResearchProfilePatch(topic="会话乙")),
    ]
    provider = MockProvider(
        [
            ProviderResult(
                Message("assistant", (ContentBlock("text", {"text": item.model_dump_json()}),))
            )
            for item in decisions
        ]
    )
    generator = RuntimeConversationDecisionGenerator(
        provider_factory=lambda: provider,
        timeout_seconds=1,
    )
    with SessionLocal() as db:
        first_service = ResearchConversationService(decision_generator=generator)
        first = first_service.create(
            CreateResearchConversationRequest(initial_message="甲的第一轮"), db
        )
        rebuilt_service = ResearchConversationService(decision_generator=generator)
        rebuilt_service.send_message(
            first.conversation_id,
            SendResearchMessageRequest(message="甲的第二轮"),
            db,
        )
        calls_before_get = len(provider.calls)
        rebuilt_service.get(first.conversation_id, db)
        assert len(provider.calls) == calls_before_get
        rebuilt_service.create(
            CreateResearchConversationRequest(initial_message="乙的第一轮"), db
        )

    second_call = provider.calls[1]["messages"]
    assert [item["role"] for item in second_call] == ["system", "user", "assistant", "user"]
    assert second_call[1]["content"][0]["text"] == "甲的第一轮"
    assert second_call[2]["content"][0]["text"] == "第一轮回复"
    assert json.loads(second_call[3]["content"][0]["text"])["latest_user_message"] == "甲的第二轮"
    assert [item["role"] for item in provider.calls[2]["messages"]] == ["system", "user"]


def test_rebuilt_service_restores_confirmed_context_for_the_next_run() -> None:
    decision = _decision(reply="继续基于已确认背景澄清")
    provider = MockProvider(
        [
            ProviderResult(
                Message(
                    "assistant",
                    (ContentBlock("text", {"text": decision.model_dump_json()}),),
                )
            )
        ]
    )
    provenance = ConfirmedContextProvenance(
        transfer_id="transfer-restored",
        source_module="learning",
        source_object=ContextSourceObject(type="notebook_item", id="note-restored"),
        source_scope_id="learning-session-restored",
        target_module="research",
        topic="已确认主题",
        summary="已确认摘要",
        selected_content=[],
        confirmed_at=datetime.now(UTC),
    )
    with SessionLocal() as db:
        created = ResearchConversationService().create_from_confirmed_context(provenance, db)
        rebuilt = ResearchConversationService(
            decision_generator=RuntimeConversationDecisionGenerator(
                provider_factory=lambda: provider,
                timeout_seconds=1,
            )
        )
        rebuilt.send_message(
            created.conversation_id,
            SendResearchMessageRequest(message="继续澄清"),
            db,
        )

    sent = provider.calls[0]["messages"]
    # 确认上下文创建不再预写 assistant 开场（开场白由学习上下文 PUT 后的
    # 桥接欢迎语负责），因此此场景的历史只有用户带入记录与本次输入。
    assert [item["role"] for item in sent] == ["system", "user", "user"]
    payload = json.loads(sent[-1]["content"][0]["text"])
    assert payload["confirmed_learning_context"]["topic"] == "已确认主题"


def test_confirmed_context_defers_welcome_to_learning_context_bridge() -> None:
    """确认上下文只登记用户带入记录；开场白由学习上下文 PUT 后的桥接欢迎语负责。"""
    provenance = ConfirmedContextProvenance(
        transfer_id="transfer-opening-summary",
        source_module="learning",
        source_object=ContextSourceObject(type="notebook_item", id="note-opening"),
        source_scope_id="learning-session-opening",
        target_module="research",
        topic="学习困难预测",
        summary="已确认的学习背景：用户比较关注公开课程数据中的学习困难预测。",
        selected_content=[],
        confirmed_at=datetime.now(UTC),
    )

    with SessionLocal() as db:
        created = ResearchConversationService().create_from_confirmed_context(provenance, db)

    assert [message.role for message in created.messages] == ["user"]
    assert provenance.summary in created.messages[-1].content
    all_text = "\n".join(message.content for message in created.messages)
    assert "学习背景开场总结" not in all_text
    for marker in ("描述想法", "整理科研画像", "主动检索与记录"):
        assert marker not in all_text


def test_entry_branch_choice_does_not_become_a_confirmed_research_topic(
    client: TestClient,
) -> None:
    created = client.post("/api/v1/research/conversations", json={})
    conversation_id = created.json()["conversation_id"]

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/messages",
        json={"message": "已有研究兴趣：我想围绕一个主题继续研究"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["topic"] is None
    assert body["recommended_action"] == "continue_dialogue"
    assert "正式题目" in body["next_question"]


def test_context_assembler_reuses_summary_boundary_without_resummarizing_covered_messages() -> None:
    class RecordingCompactor(ConversationCompactor):
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def compact(
            self,
            previous_summary: str | None,
            messages: tuple[ResearchConversationMessage, ...],
            budget_tokens: int,
        ) -> str:
            self.calls.append([message.message_id for message in messages])
            return super().compact(previous_summary, messages, budget_tokens)

    now = datetime.now(UTC)
    messages = [
        ResearchConversationMessage(
            message_id=f"message-{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=f"history-{index}-" + ("x" * 180),
            created_at=now,
        )
        for index in range(8)
    ]
    profile = ResearchProfile(topic="预算测试")
    runtime_input = build_research_conversation_input(profile, "继续", None)
    fixed_tokens = len(research_conversation_agent.system_prompt) + len(runtime_input)
    recorder = RecordingCompactor()
    assembler = ResearchContextAssembler(
        budget_tokens=fixed_tokens + 450,
        summary_budget_tokens=80,
        compactor=recorder,
    )

    first = assembler.assemble(
        ResearchContextInput(
            messages,
            research_conversation_agent.system_prompt,
            runtime_input,
            None,
        )
    )
    extended = messages + [
        ResearchConversationMessage(
            message_id=f"message-{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=f"history-{index}-" + ("y" * 180),
            created_at=now,
        )
        for index in range(8, 10)
    ]
    second = assembler.assemble(
        ResearchContextInput(
            extended,
            research_conversation_agent.system_prompt,
            runtime_input,
            first.pending_summary,
        )
    )

    assert first.pending_summary is not None
    assert second.pending_summary is not None
    assert first.token_count <= assembler.budget_tokens
    assert second.token_count <= assembler.budget_tokens
    covered_first = set(recorder.calls[0])
    assert covered_first.isdisjoint(recorder.calls[1])
    assert second.pending_summary.source_message_count > first.pending_summary.source_message_count
    assert second.pending_summary.through_message_id == recorder.calls[1][-1]


def test_service_persists_and_reuses_budgeted_context_summary_across_runs() -> None:
    now = datetime.now(UTC)
    stored_messages = [
        ResearchConversationMessage(
            message_id=f"stored-{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=f"stored history {index} " + ("长" * 300),
            created_at=now,
        )
        for index in range(6)
    ]
    profile = ResearchProfile(topic="长对话")
    runtime_input = build_research_conversation_input(profile, "继续研究", None)
    budget = len(research_conversation_agent.system_prompt) + len(runtime_input) + 500
    assembler = ResearchContextAssembler(budget_tokens=budget, summary_budget_tokens=100)
    decisions = [_decision(reply="第一轮压缩后回复"), _decision(reply="复用摘要后的回复")]
    provider = MockProvider(
        [
            ProviderResult(
                Message("assistant", (ContentBlock("text", {"text": item.model_dump_json()}),))
            )
            for item in decisions
        ]
    )
    generator = RuntimeConversationDecisionGenerator(
        provider_factory=lambda: provider,
        timeout_seconds=1,
    )
    with SessionLocal() as db:
        model = ResearchConversationModel(
            profile_data=profile.model_dump(mode="json"),
            messages_data=[item.model_dump(mode="json") for item in stored_messages],
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        conversation_id = model.id
        ResearchConversationService(
            decision_generator=generator,
            context_assembler=assembler,
        ).send_message(
            conversation_id,
            SendResearchMessageRequest(message="继续研究"),
            db,
        )
        db.refresh(model)
        first_summary = dict(model.context_summary_data)
        ResearchConversationService(
            decision_generator=generator,
            context_assembler=assembler,
        ).send_message(
            conversation_id,
            SendResearchMessageRequest(message="再继续"),
            db,
        )
        db.refresh(model)
        second_summary = dict(model.context_summary_data)

    first_call = provider.calls[0]["messages"]
    assert first_call[0]["pinned"] is True
    assert first_call[-1]["pinned"] is True
    assert any(
        item["metadata"].get("context_kind") == "research_conversation_summary"
        and item["pinned"] is False
        for item in first_call
    )
    assert sum(
        len(str(block.get("text", "")))
        for item in first_call
        for block in item["content"]
    ) <= budget
    assert first_summary == second_summary
    assert first_summary["generation_mode"] == "rules"
    assert first_summary["run_id"].startswith("context-summary-")


def test_compaction_failure_keeps_the_previous_valid_summary() -> None:
    class FailingCompactor:
        def compact(self, *args: object, **kwargs: object) -> str:
            raise RuntimeError("summary failed")

    now = datetime.now(UTC)
    messages = [
        ResearchConversationMessage(
            message_id=f"failure-{index}",
            role="user" if index % 2 == 0 else "assistant",
            content="原始历史" + ("x" * 300),
            created_at=now,
        )
        for index in range(4)
    ]
    previous = ResearchContextSummary(
        summary="上一个有效摘要",
        through_message_id="failure-0",
        source_message_count=1,
        generation_mode="rules",
        run_id="context-summary-valid",
    )
    fake = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(reply="仍使用原始消息完成本轮"),
                run_id="decision-after-summary-failure",
                event_count=1,
            )
        ]
    )
    with SessionLocal() as db:
        model = ResearchConversationModel(
            profile_data=ResearchProfile(topic="压缩失败测试").model_dump(mode="json"),
            messages_data=[item.model_dump(mode="json") for item in messages],
            context_summary_data=previous.model_dump(mode="json"),
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        runtime_input = build_research_conversation_input(
            ResearchProfile(topic="压缩失败测试"), "继续", None
        )
        budget = len(research_conversation_agent.system_prompt) + len(runtime_input) + 100
        ResearchConversationService(
            decision_generator=fake,
            context_assembler=ResearchContextAssembler(
                budget_tokens=budget,
                summary_budget_tokens=50,
                compactor=FailingCompactor(),
            ),
        ).send_message(model.id, SendResearchMessageRequest(message="继续"), db)
        db.refresh(model)

        assert model.context_summary_data == previous.model_dump(mode="json")
        history = fake.calls[0]["conversation_history"]
        assert len(history) == len(messages)


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
        conversation_history=(),
        user_message="我有一个约束",
        conversation_id="conversation-invalid-patch",
    )

    assert outcome.status == "failed"
    assert outcome.decision is None


def test_missing_conversation_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/research/conversations/missing")

    assert response.status_code == 404


def _failed_outcome() -> ConversationDecisionOutcome:
    return ConversationDecisionOutcome(
        status="failed",
        reason="fake provider exploded",
    )


def test_retry_failed_reply_regenerates_without_duplicating_user_message(
    client: TestClient,
) -> None:
    fake = FakeDecisionGenerator(
        [
            _failed_outcome(),
            ConversationDecisionOutcome.generated(
                _decision(
                    reply="重试后由模型生成的回复。",
                    intent="clarify",
                    profile_patch=ResearchProfilePatch(topic="图神经网络复现"),
                ),
                run_id="run-retry-success",
                event_count=5,
            ),
        ]
    )
    _conversation_service.decision_generator = fake

    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究图神经网络复现"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]
    failed_body = created.json()
    assert failed_body["messages"][-1]["generation_mode"] == "rules_fallback"

    retried = client.post(f"/api/v1/research/conversations/{conversation_id}/messages/retry-last")

    assert retried.status_code == 200
    body = retried.json()
    messages = body["messages"]
    assert [m["role"] for m in messages].count("user") == 1
    assert all(m["generation_mode"] != "rules_fallback" for m in messages)
    assert messages[-1]["content"] == "重试后由模型生成的回复。"
    assert messages[-1]["generation_mode"] == "agent"
    assert messages[-1]["run_id"] == "run-retry-success"
    assert body["profile"]["topic"] == "图神经网络复现"


def test_retry_without_failed_reply_is_rejected(client: TestClient) -> None:
    fake = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(reply="正常回复。"),
                run_id="run-ok",
                event_count=2,
            )
        ]
    )
    _conversation_service.decision_generator = fake

    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究教育人工智能"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]

    retried = client.post(f"/api/v1/research/conversations/{conversation_id}/messages/retry-last")

    assert retried.status_code == 409
    assert "没有可重试" in retried.json()["detail"]


def test_retry_failure_keeps_user_message_and_last_success(client: TestClient) -> None:
    fake = FakeDecisionGenerator(
        [
            ConversationDecisionOutcome.generated(
                _decision(reply="第一次成功回复。"),
                run_id="run-first-ok",
                event_count=3,
            ),
            _failed_outcome(),
            _failed_outcome(),
        ]
    )
    _conversation_service.decision_generator = fake

    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究教育人工智能"},
    )
    conversation_id = created.json()["conversation_id"]
    failed_send = client.post(
        f"/api/v1/research/conversations/{conversation_id}/messages",
        json={"message": "补充一些约束条件"},
    )
    assert failed_send.status_code == 200
    before = failed_send.json()
    assert before["messages"][-1]["generation_mode"] == "rules_fallback"
    user_count_before = [m["role"] for m in before["messages"]].count("user")

    retried = client.post(f"/api/v1/research/conversations/{conversation_id}/messages/retry-last")

    assert retried.status_code == 422
    detail = retried.json()["detail"]
    assert detail["code"] == "research_generation_failed"

    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    after = restored.json()
    assert [m["role"] for m in after["messages"]].count("user") == user_count_before
    assert after["messages"][-1]["generation_mode"] == "rules_fallback"
    assert any(m["content"] == "第一次成功回复。" for m in after["messages"])


def test_retry_missing_conversation_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/research/conversations/missing/messages/retry-last")

    assert response.status_code == 404
