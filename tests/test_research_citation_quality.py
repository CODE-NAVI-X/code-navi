"""Contracts for explicit, offline citation-quality checks."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, engine  # noqa: E402
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


class FakeArxivSource:
    def __init__(self, papers: list[PaperMetadata]) -> None:
        self.papers = papers

    def search(self, query: str) -> AcademicSourceResult:
        assert query
        return AcademicSourceResult.success("arxiv", self.papers)


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
                    constraints=["两周"],
                    expected_output="课程项目报告",
                ),
                candidate_questions=["即时反馈是否改善 Python 练习表现？"],
                assumptions=[],
                uncertainties=["伦理与随机分组待确认"],
                next_question="是否查看计划？",
                suggested_answers=["查看计划", "补充条件", "继续讨论"],
                recommended_action="review_profile",
            ),
            run_id="citation-quality-ready",
            event_count=1,
        )


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
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


def _paper(*, title: str, complete: bool = True) -> PaperMetadata:
    return PaperMetadata(
        title=title,
        authors=["Ada Lovelace"] if complete else [],
        year=2025 if complete else None,
        source_name="arXiv" if complete else "",
        url=f"https://arxiv.org/abs/{'2501.00001' if complete else '2501.00002'}",
        identifier="arXiv:2501.00001" if complete else None,
        abstract_excerpt=(
            "We compare feedback systems in a controlled learning study."
            if complete
            else None
        ),
        accessed_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def _conversation(client: TestClient) -> str:
    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我研究 Python 反馈"},
    )
    assert response.status_code == 201
    return response.json()["conversation_id"]


def _bundle(client: TestClient, conversation_id: str) -> dict[str, object]:
    _conversation_search_service.search_tool = AcademicSearchTool(
        {
            "arxiv": FakeArxivSource(
                [
                    _paper(title="Complete Feedback Study"),
                    _paper(title="Incomplete Feedback Study", complete=False),
                ]
            )
        }
    )
    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"query": "Python feedback", "sources": ["arxiv"]},
    )
    assert response.status_code == 200
    return response.json()


def _select(
    client: TestClient,
    conversation_id: str,
    bundle: dict[str, object],
    *,
    paper_index: int,
    target_section: str,
    paragraph_anchor: str,
) -> dict[str, object]:
    paper = bundle["papers"][paper_index]
    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/selected-citations",
        json={
            "evidence_bundle_id": bundle["bundle_id"],
            "paper_url": paper["url"],
            "target_document": "paper_draft",
            "target_section": target_section,
            "paragraph_anchor": paragraph_anchor,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_quality_check_returns_and_persists_a_safe_empty_state(client: TestClient) -> None:
    conversation_id = _conversation(client)

    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/citation-quality-checks"
    )
    restored = client.get(
        f"/api/v1/research/conversations/{conversation_id}/citation-quality-checks"
    )

    assert created.status_code == 201
    assert created.json()["quality_status"] == "empty"
    assert created.json()["selected_source_count"] == 0
    assert created.json()["coverage_items"] == []
    assert created.json()["metadata_gaps"] == []
    assert "先主动选择" in created.json()["empty_state_message"]
    assert restored.status_code == 200
    assert restored.json()[0]["check_id"] == created.json()["check_id"]


def test_quality_check_maps_sections_and_reports_duplicates_gaps_and_placeholders(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = _conversation(client)
    bundle = _bundle(client, conversation_id)
    first = _select(
        client,
        conversation_id,
        bundle,
        paper_index=0,
        target_section="相关工作",
        paragraph_anchor="相关工作-1",
    )
    duplicate = _select(
        client,
        conversation_id,
        bundle,
        paper_index=0,
        target_section="相关工作",
        paragraph_anchor="相关工作-1",
    )
    incomplete = _select(
        client,
        conversation_id,
        bundle,
        paper_index=1,
        target_section="方法",
        paragraph_anchor="方法-1",
    )
    monkeypatch.setattr(
        _conversation_search_service,
        "search",
        lambda *_args, **_kwargs: pytest.fail("引用质量检查不得联网检索"),
    )

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/citation-quality-checks"
    )

    assert response.status_code == 201
    result = response.json()
    assert result["quality_status"] == "needs_review"
    assert result["selected_source_count"] == 3
    assert result["unique_source_count"] == 2
    assert {item["target_section"] for item in result["coverage_items"]} == {
        "相关工作",
        "方法",
    }
    duplicate_ids = result["duplicate_selections"][0]["selected_citation_ids"]
    assert set(duplicate_ids) == {
        first["selected_citation_id"],
        duplicate["selected_citation_id"],
    }
    assert len(result["uninserted_placeholders"]) == 3
    assert incomplete["selected_citation_id"] in {
        item["selected_citation_ids"][0] for item in result["metadata_gaps"]
    }
    assert all(item["classification"] == "to_verify" for item in result["metadata_gaps"])
    assert all(item["classification"] == "inference" for item in result["coverage_items"])


def test_quality_check_is_conversation_scoped_and_respects_inserted_status(
    client: TestClient,
) -> None:
    first_conversation = _conversation(client)
    first_bundle = _bundle(client, first_conversation)
    first_selection = _select(
        client,
        first_conversation,
        first_bundle,
        paper_index=0,
        target_section="引言",
        paragraph_anchor="引言-1",
    )
    second_conversation = _conversation(client)
    second_bundle = _bundle(client, second_conversation)
    _select(
        client,
        second_conversation,
        second_bundle,
        paper_index=1,
        target_section="讨论",
        paragraph_anchor="讨论-1",
    )
    updated = client.patch(
        f"/api/v1/research/selected-citations/{first_selection['selected_citation_id']}",
        json={"status": "inserted"},
    )
    assert updated.status_code == 200

    first_check = client.post(
        f"/api/v1/research/conversations/{first_conversation}/citation-quality-checks"
    )
    second_check = client.post(
        f"/api/v1/research/conversations/{second_conversation}/citation-quality-checks"
    )

    assert first_check.status_code == 201
    assert first_check.json()["selected_source_count"] == 1
    assert first_check.json()["uninserted_placeholders"] == []
    assert first_check.json()["metadata_gaps"] == []
    assert second_check.json()["selected_source_count"] == 1
    assert second_check.json()["metadata_gaps"]
    assert first_selection["selected_citation_id"] not in second_check.text
