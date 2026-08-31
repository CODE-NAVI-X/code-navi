"""Failure-contract, persistence and prompt-context tests for LLM research content."""

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
from code_navi.research.conversation_plan import build_llm_research_plan  # noqa: E402
from code_navi.research.conversation_schemas import (  # noqa: E402
    ResearchProfile,
    ResearchProfilePatch,
)
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome  # noqa: E402
from code_navi.research.research_generation import (  # noqa: E402
    ResearchGenerationError,
    require_generated_artifact,
)
from code_navi.research.router import _conversation_service  # noqa: E402
from code_navi.server import app  # noqa: E402
from research_llm_fakes import ContextAwareArtifactGenerator  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_generators() -> Generator[None, None, None]:
    decision = _conversation_service.decision_generator
    artifact = _conversation_service.artifact_generator
    yield
    _conversation_service.decision_generator = decision
    _conversation_service.artifact_generator = artifact


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


class ReadyDecisionGenerator:
    def generate(self, **_: object) -> ConversationDecisionOutcome:
        return ConversationDecisionOutcome.generated(
            ResearchConversationDecision(
                reply="研究画像已整理。",
                intent="clarify",
                profile_patch=ResearchProfilePatch(
                    topic="生成式 AI 编程学习反馈",
                    research_questions=["即时反馈是否改善 Python 练习表现？"],
                    context="30 名本科生课程",
                    methods=["小规模对照研究"],
                    data_requirements="匿名学习记录",
                    constraints=["两周", "没有 GPU"],
                    expected_output="课程项目报告",
                ),
                candidate_questions=["即时反馈是否改善 Python 练习表现？"],
                recommended_action="review_profile",
            ),
            run_id="test-ready",
            event_count=1,
        )


class StaticArtifactGenerator:
    def __init__(self, outcome: ArtifactLlmOutcome) -> None:
        self.outcome = outcome

    def generate(self, **_: object) -> ArtifactLlmOutcome:
        return self.outcome


def _plan_json() -> str:
    entry = {
        "content": "模型建议先确认一个可观察结果。",
        "classification": "inference",
        "basis": "已确认科研画像。",
    }
    return __import__("json").dumps(
        {
            "research_title": entry,
            "research_goal": entry,
            "candidate_methods_or_baselines": [entry],
            "suggested_datasets_or_metrics": [
                {
                    "content": "数据范围待核验。",
                    "classification": "to_verify",
                    "basis": "画像未覆盖。",
                }
            ],
            "two_week_mvp_plan": [entry],
            "risks_and_mitigations": [{"risk": entry, "mitigation": entry}],
            "suggested_search_keywords": ["研究主题"],
            "pending_items": [],
            "provenance_note": "模型生成。",
        },
        ensure_ascii=False,
    )


def test_research_plan_is_generated_with_llm_metadata() -> None:
    class Generator:
        def generate(self, **_: object) -> ArtifactLlmOutcome:
            return ArtifactLlmOutcome.generated(_plan_json(), run_id="plan-run", event_count=3)

    plan = build_llm_research_plan(
        ResearchProfile(topic="图卷积网络", research_questions=["如何比较方法？"]),
        generator=Generator(),
        conversation_id="conversation-1",
    )

    assert plan is not None
    assert plan.generation_mode == "llm"
    assert plan.run_id == "plan-run"
    assert plan.event_count == 3


def test_research_plan_does_not_fallback_when_provider_is_unavailable() -> None:
    with pytest.raises(ResearchGenerationError) as error:
        build_llm_research_plan(
            ResearchProfile(topic="图卷积网络", research_questions=["如何比较方法？"]),
            generator=StaticArtifactGenerator(ArtifactLlmOutcome.unavailable()),
            conversation_id="conversation-1",
        )

    assert error.value.stage == "provider_unavailable"


def test_research_plan_rejects_invalid_model_output() -> None:
    with pytest.raises(ResearchGenerationError) as error:
        build_llm_research_plan(
            ResearchProfile(topic="图卷积网络", research_questions=["如何比较方法？"]),
            generator=StaticArtifactGenerator(ArtifactLlmOutcome.generated("{}")),
            conversation_id="conversation-1",
        )

    assert error.value.stage == "invalid_output"


def test_research_plan_endpoint_persists_and_restores_llm_plan(client: TestClient) -> None:
    generator = ContextAwareArtifactGenerator()
    _conversation_service.artifact_generator = generator
    conversation_id = _ready_conversation(client)

    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/research-plan",
        json={"user_confirmed": True},
    )

    assert created.status_code == 200
    assert created.json()["generation_mode"] == "llm"
    assert generator.calls == ["research_plan"]

    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert restored.status_code == 200
    assert restored.json()["research_plan"] == created.json()


def test_research_plan_endpoint_does_not_return_rule_template_on_failure(
    client: TestClient,
) -> None:
    _conversation_service.artifact_generator = StaticArtifactGenerator(
        ArtifactLlmOutcome.unavailable()
    )
    conversation_id = _ready_conversation(client)

    failed = client.post(
        f"/api/v1/research/conversations/{conversation_id}/research-plan",
        json={"user_confirmed": True},
    )

    assert failed.status_code == 503
    assert failed.json()["detail"]["code"] == "research_generation_failed"
    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert restored.json()["research_plan"] is None


def test_configured_model_welcome_is_persisted_as_agent_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    _conversation_service.decision_generator = ReadyDecisionGenerator()

    response = client.post("/api/v1/research/conversations", json={})

    assert response.status_code == 201
    assert response.json()["generation_mode"] == "agent"
    assert response.json()["messages"][-1]["generation_mode"] == "agent"


def _ready_conversation(client: TestClient) -> str:
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    response = client.post(
        "/api/v1/research/conversations", json={"initial_message": "我研究编程反馈"}
    )
    assert response.status_code == 201
    return response.json()["conversation_id"]


def test_require_generated_artifact_maps_outcomes_to_typed_stages() -> None:
    with pytest.raises(ResearchGenerationError) as unavailable:
        require_generated_artifact(ArtifactLlmOutcome.unavailable(), kind="k")
    assert unavailable.value.stage == "provider_unavailable"

    with pytest.raises(ResearchGenerationError) as timeout:
        require_generated_artifact(ArtifactLlmOutcome.failed("request timed out"), kind="k")
    assert timeout.value.stage == "timeout"

    with pytest.raises(ResearchGenerationError) as empty:
        require_generated_artifact(ArtifactLlmOutcome.generated(""), kind="k")
    assert empty.value.stage == "failed"

    assert require_generated_artifact(ArtifactLlmOutcome.generated("{}"), kind="k") == "{}"


def test_provider_unavailable_returns_503_and_no_rules_advice(client: TestClient) -> None:
    _conversation_service.artifact_generator = StaticArtifactGenerator(
        ArtifactLlmOutcome.unavailable()
    )
    conversation_id = _ready_conversation(client)

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/topic-difficulty-analysis",
        json={"user_confirmed": True},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "research_generation_failed"
    assert detail["stage"] == "provider_unavailable"


def test_last_successful_analysis_survives_a_failed_retry(client: TestClient) -> None:
    generator = ContextAwareArtifactGenerator()
    _conversation_service.artifact_generator = generator
    conversation_id = _ready_conversation(client)

    first = client.post(
        f"/api/v1/research/conversations/{conversation_id}/topic-difficulty-analysis",
        json={"user_confirmed": True},
    )
    assert first.status_code == 200
    assert first.json()["generation_mode"] == "llm"

    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert restored.json()["topic_difficulty_analysis"]["generation_mode"] == "llm"

    _conversation_service.artifact_generator = StaticArtifactGenerator(
        ArtifactLlmOutcome.unavailable()
    )
    failed = client.post(
        f"/api/v1/research/conversations/{conversation_id}/topic-difficulty-analysis",
        json={"user_confirmed": True},
    )
    assert failed.status_code == 503

    after_failure = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert after_failure.json()["topic_difficulty_analysis"]["generation_mode"] == "llm"


def test_user_triggered_mindmap_persists_and_failed_retry_keeps_last_success(
    client: TestClient,
) -> None:
    generator = ContextAwareArtifactGenerator()
    _conversation_service.artifact_generator = generator
    conversation_id = _ready_conversation(client)

    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/research-mindmap",
        json={"user_confirmed": True},
    )

    assert created.status_code == 200
    assert created.json()["generation_mode"] == "llm"
    assert created.json()["run_id"] == "test-run"
    assert generator.calls == ["research_mindmap"]
    assert generator.contexts[0]["source_boundary"]["program_controls"]

    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert restored.json()["research_mindmap"]["generation_mode"] == "llm"

    _conversation_service.artifact_generator = StaticArtifactGenerator(
        ArtifactLlmOutcome.unavailable()
    )
    failed = client.post(
        f"/api/v1/research/conversations/{conversation_id}/research-mindmap",
        json={"user_confirmed": True},
    )
    assert failed.status_code == 503
    assert failed.json()["detail"]["message"] == "模型生成失败，本次未生成科研建议。请重试。"

    after_failure = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert after_failure.json()["research_mindmap"]["generation_mode"] == "llm"


def test_experiment_design_persists_and_restores_last_success(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conversation_id = _ready_conversation(client)

    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/experiment-design",
        json={"user_confirmed": True},
    )
    assert created.status_code == 200
    assert created.json()["generation_mode"] == "llm"

    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert restored.json()["experiment_design"]["generation_mode"] == "llm"


def test_difficulty_prompt_carries_profile_plan_and_source_boundary(client: TestClient) -> None:
    generator = ContextAwareArtifactGenerator()
    _conversation_service.artifact_generator = generator
    conversation_id = _ready_conversation(client)

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/topic-difficulty-analysis",
        json={"user_confirmed": True},
    )

    assert response.status_code == 200
    context = generator.contexts[0]
    assert context["profile"]["topic"] == "生成式 AI 编程学习反馈"
    assert context["research_plan"] is not None
    assert "source_boundary" in context
    assert "required_json_shape" in context


def test_model_cannot_promote_to_verify_to_fact_via_router(client: TestClient) -> None:
    _conversation_service.artifact_generator = StaticArtifactGenerator(
        ArtifactLlmOutcome.generated(
            '{"title":"t","information_scope":"profile_and_plan_only",'
            '"items":[{"area":"a","content":"c","classification":"fact","basis":"b",'
            '"source_scope":"profile_and_plan_only"}],"provenance_note":"p"}'
        )
    )
    conversation_id = _ready_conversation(client)

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/topic-difficulty-analysis",
        json={"user_confirmed": True},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["stage"] == "invalid_output"
