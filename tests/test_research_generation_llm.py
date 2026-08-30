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
from code_navi.research.conversation_schemas import ResearchProfilePatch  # noqa: E402
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
