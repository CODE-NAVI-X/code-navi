"""Offline handoff tests from research clarification to academic search."""

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
)
from code_navi.research.conversation_schemas import (  # noqa: E402
    ResearchConversationDecision,
    ResearchProfilePatch,
)
from code_navi.research.router import (  # noqa: E402
    _conversation_search_service,
    _conversation_service,
)
from code_navi.research.skill_runtime import load_academic_search_skill  # noqa: E402
from code_navi.server import app  # noqa: E402


class ReadyDecisionGenerator:
    def generate(self, **_kwargs: object) -> ConversationDecisionOutcome:
        decision = ResearchConversationDecision(
            reply="科研画像已准备好，可以先检查检索计划。",
            intent="prepare_search",
            profile_patch=ResearchProfilePatch(
                topic="生成式 AI 辅助编程学习",
                research_questions=["不同提示策略如何影响学习效果？"],
                context="本科编程课程",
                methods=["对照实验"],
                data_requirements="公开数据与课程记录",
            ),
            candidate_questions=["不同提示策略如何影响学习效果？"],
            recommended_action="prepare_search",
        )
        return ConversationDecisionOutcome.generated(
            decision,
            run_id="run-search-ready",
            event_count=2,
        )


class FakeSource:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str) -> AcademicSourceResult:
        self.calls += 1
        return AcademicSourceResult.success(
            "arxiv",
            [
                PaperMetadata(
                    title="Generative AI in Programming Education",
                    authors=["Ada Example"],
                    year=2025,
                    source_name="arXiv",
                    url="https://arxiv.org/abs/2501.00001",
                    identifier="arXiv:2501.00001",
                    abstract_excerpt=f"Evidence for {query}",
                    accessed_at=datetime(2026, 8, 3, tzinfo=UTC),
                )
            ],
        )


@pytest.fixture(autouse=True)
def isolated_services() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    original_generator = _conversation_service.decision_generator
    original_tool = _conversation_search_service.search_tool
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    yield
    _conversation_service.decision_generator = original_generator
    _conversation_search_service.search_tool = original_tool
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_search_plan_uses_profile_fields_without_calling_a_source(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()

    response = client.get(
        f"/api/v1/research/conversations/{created['conversation_id']}/search-plan"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "research-search-plan.v1"
    assert body["user_confirmation_required"] is True
    assert "生成式 AI 辅助编程学习" in body["query"]
    assert "本科编程课程" in body["query"]
    assert source.calls == 0


def test_explicit_conversation_search_dispatches_registered_tool(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/evidence-bundles",
        json={"sources": ["arxiv"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "academic-evidence.v1"
    assert body["conversation_id"] == created["conversation_id"]
    assert body["papers"][0]["title"] == "Generative AI in Programming Education"
    assert body["tool_audit"]["required_permissions"] == ["NETWORK", "READ"]
    assert source.calls == 1


def test_repeated_search_uses_persistent_cache_and_restores_bundle(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()
    url = f"/api/v1/research/conversations/{created['conversation_id']}/evidence-bundles"

    first = client.post(url, json={"query": "AI programming education", "sources": ["arxiv"]})
    second = client.post(url, json={"query": " AI  programming education ", "sources": ["arxiv"]})
    restored = client.get(url)

    assert first.status_code == 200
    assert first.json()["cache_hit"] is False
    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second.json()["bundle_id"] == first.json()["bundle_id"]
    assert source.calls == 1
    assert restored.status_code == 200
    assert len(restored.json()) == 1
    assert restored.json()[0]["bundle_id"] == first.json()["bundle_id"]


def test_sparse_conversation_cannot_start_network_search(client: TestClient) -> None:
    _conversation_service.decision_generator = type(
        "UnavailableGenerator",
        (),
        {"generate": lambda self, **kwargs: ConversationDecisionOutcome.unavailable()},
    )()
    created = client.post("/api/v1/research/conversations", json={}).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/evidence-bundles",
        json={"sources": ["arxiv"]},
    )

    assert response.status_code == 409


def test_academic_search_skill_contract_is_packaged() -> None:
    skill = load_academic_search_skill()

    assert "explicit user confirmation" in skill
    assert "metadata_and_abstract_only" in skill
    assert "Do not fall back to a browser or unrestricted web search" in skill
