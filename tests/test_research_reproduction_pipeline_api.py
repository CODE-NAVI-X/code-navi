"""API contract for a user-selected local paper reproduction Pipeline."""

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
            run_id="pipeline-api",
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


class ForbiddenSearchTool:
    def search(self, *_: object, **__: object) -> object:
        raise AssertionError("Pipeline generation must not start a search.")


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


def test_pipeline_requires_a_saved_selected_paper_and_restores_without_search() -> None:
    with TestClient(app) as client:
        conversation_id = client.post(
            "/api/v1/research/conversations", json={"initial_message": "prompt learning"}
        ).json()["conversation_id"]
        no_selection = client.post(
            f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines", json={}
        )
        bundle = client.post(
            f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
            json={"sources": ["arxiv"]},
        ).json()
        previous_tool = _conversation_search_service.search_tool
        _conversation_search_service.search_tool = ForbiddenSearchTool()  # type: ignore[assignment]
        try:
            missing = client.post(
                f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines",
                json={
                    "evidence_bundle_id": bundle["bundle_id"],
                    "paper_url": "https://example.test/missing",
                },
            )
            conditions = client.put(
                f"/api/v1/research/conversations/{conversation_id}/reproduction-conditions",
                json={
                    "hardware": "8 核 CPU",
                    "available_time": "两周",
                    "reproduction_goal": "核对训练流程与指标记录",
                },
            )
            assert conditions.status_code == 200
            created = client.post(
                f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines",
                json={
                    "evidence_bundle_id": bundle["bundle_id"],
                    "paper_url": bundle["papers"][0]["url"],
                },
            )
            restored = client.get(
                f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines"
            )
            by_id = client.get(
                f"/api/v1/research/reproduction-pipelines/{created.json()['pipeline_id']}"
            )
        finally:
            _conversation_search_service.search_tool = previous_tool

    assert no_selection.status_code == 422
    assert missing.status_code == 404
    assert created.status_code == 201
    assert created.json()["selected_paper"]["url"] == bundle["papers"][0]["url"]
    assert restored.status_code == 200
    assert restored.json()[0]["pipeline_id"] == created.json()["pipeline_id"]
    assert by_id.status_code == 200
    assert by_id.json()["schema_version"] == "reproduction-pipeline.v1"
