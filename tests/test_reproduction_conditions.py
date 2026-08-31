"""Checkpoint-4 contracts: reproduction conditions are collected before planning.

The pipeline must refuse to fabricate hardware, time or goal assumptions: the
user supplies device/time/goal conditions first, they are stored as
user-provided facts, and the generated plan records them plus explicit
acceptance criteria instead of inventing CUDA, dataset scale or durations.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.research.academic import (  # noqa: E402
    AcademicSearchTool,
    AcademicSourceResult,
    PaperMetadata,
)
from code_navi.research.conversation_agent import (  # noqa: E402
    ConversationDecisionOutcome,
    ResearchConversationDecision,
)
from code_navi.research.conversation_schemas import ResearchProfilePatch  # noqa: E402
from code_navi.research.router import (  # noqa: E402
    _conversation_search_service,
    _conversation_service,
)
from code_navi.server import app  # noqa: E402
from research_llm_fakes import ContextAwareArtifactGenerator  # noqa: E402


class ReadyGenerator:
    def generate(self, **_: object) -> ConversationDecisionOutcome:
        return ConversationDecisionOutcome.generated(
            ResearchConversationDecision(
                reply="ready",
                intent="prepare_search",
                profile_patch=ResearchProfilePatch(
                    topic="Prompt learning",
                    research_questions=["Which prompt helps?"],
                    context="A course comparison exercise",
                    methods=["baseline comparison"],
                ),
                recommended_action="prepare_search",
            ),
            run_id="conditions-api",
            event_count=1,
        )


class LocalSource:
    def search(self, _: str) -> AcademicSourceResult:
        return AcademicSourceResult.success(
            "arxiv",
            [
                PaperMetadata(
                    title="Local saved paper",
                    authors=["Ada"],
                    year=2025,
                    source_name="arXiv",
                    url="https://example.test/local-paper",
                    identifier="arXiv:2501.1",
                    abstract_excerpt="This abstract describes a prompt comparison.",
                    accessed_at=datetime(2026, 8, 15, tzinfo=UTC),
                )
            ],
        )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


FULL_CONDITIONS = {
    "hardware": "无独立 GPU，使用 8 核 CPU",
    "vram": "无独显",
    "operating_system": "Windows 11",
    "python_environment": "Python 3.11 venv",
    "available_time": "两周，每天约 2 小时",
    "reproduction_goal": "在 Cora 上核对 GCN 的训练流程与指标记录方式",
}


@pytest.fixture(autouse=True)
def isolated_services() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    original_generator = _conversation_service.decision_generator
    original_tool = _conversation_search_service.search_tool
    original_artifact = _conversation_service.artifact_generator
    _conversation_service.decision_generator = ReadyGenerator()
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": LocalSource()})
    yield
    _conversation_service.decision_generator = original_generator
    _conversation_service.artifact_generator = original_artifact
    _conversation_search_service.search_tool = original_tool
    Base.metadata.drop_all(bind=engine)


def _ready_conversation_with_paper(client: TestClient) -> tuple[str, dict[str, object]]:
    conversation_id = client.post(
        "/api/v1/research/conversations", json={"initial_message": "prompt learning"}
    ).json()["conversation_id"]
    bundle = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"sources": ["arxiv"]},
    ).json()
    return conversation_id, bundle


def test_reproduction_conditions_save_and_restore(client: TestClient) -> None:
    conversation_id, _ = _ready_conversation_with_paper(client)

    saved = client.put(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-conditions",
        json=FULL_CONDITIONS,
    )
    assert saved.status_code == 200
    assert saved.json()["reproduction_conditions"]["hardware"] == FULL_CONDITIONS["hardware"]

    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")
    assert restored.status_code == 200
    conditions = restored.json()["reproduction_conditions"]
    assert conditions["available_time"] == FULL_CONDITIONS["available_time"]
    assert conditions["reproduction_goal"] == FULL_CONDITIONS["reproduction_goal"]

    other = client.post(
        "/api/v1/research/conversations", json={"initial_message": "另一个会话"}
    ).json()["conversation_id"]
    untouched = client.get(f"/api/v1/research/conversations/{other}")
    assert untouched.json()["reproduction_conditions"] is None


def test_pipeline_requires_hardware_time_and_goal_before_generating(
    client: TestClient,
) -> None:
    conversation_id, bundle = _ready_conversation_with_paper(client)

    refused = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines",
        json={
            "evidence_bundle_id": bundle["bundle_id"],
            "paper_url": bundle["papers"][0]["url"],
        },
    )
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["code"] == "reproduction_conditions_missing"
    joined = " ".join(detail["missing"])
    assert "硬件" in joined and "时间" in joined and "目标" in joined

    partial = dict(FULL_CONDITIONS)
    partial.pop("available_time")
    client.put(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-conditions",
        json=partial,
    )
    still_refused = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines",
        json={
            "evidence_bundle_id": bundle["bundle_id"],
            "paper_url": bundle["papers"][0]["url"],
        },
    )
    assert still_refused.status_code == 409
    assert len(still_refused.json()["detail"]["missing"]) == 1


def test_pipeline_records_user_conditions_and_acceptance_criteria(
    client: TestClient,
) -> None:
    conversation_id, bundle = _ready_conversation_with_paper(client)
    client.put(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-conditions",
        json=FULL_CONDITIONS,
    )

    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines",
        json={
            "evidence_bundle_id": bundle["bundle_id"],
            "paper_url": bundle["papers"][0]["url"],
        },
    )
    assert created.status_code == 201
    pipeline = created.json()

    assert pipeline["acceptance_criteria"], "plan must include acceptance criteria"
    resource_text = " ".join(item["content"] for item in pipeline["resources"])
    assert "8 核 CPU" in resource_text
    assert "两周" in resource_text
    user_based = [
        item
        for item in pipeline["resources"]
        if item["classification"] == "fact" and "用户" in item["basis"]
    ]
    assert user_based, "user-provided conditions must stay user-sourced facts"

    goal = pipeline["reproduction_goal"]["content"]
    assert "Cora" in goal
