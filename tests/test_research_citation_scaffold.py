"""Contracts for user-selected citation placeholders from saved evidence only."""

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
    def __init__(self, paper: PaperMetadata) -> None:
        self.paper = paper
        self.calls = 0

    def search(self, query: str) -> AcademicSourceResult:
        self.calls += 1
        assert query
        return AcademicSourceResult.success("arxiv", [self.paper])


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
                assumptions=[],
                uncertainties=["伦理与随机分组待确认"],
                next_question="是否查看计划？",
                suggested_answers=["查看计划", "补充条件", "继续讨论"],
                recommended_action="review_profile",
            ),
            run_id="test-ready",
            event_count=1,
        )


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_services() -> Generator[None, None, None]:
    decision = _conversation_service.decision_generator
    search_tool = _conversation_search_service.search_tool
    yield
    _conversation_service.decision_generator = decision
    _conversation_search_service.search_tool = search_tool


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _paper(*, complete: bool = True) -> PaperMetadata:
    return PaperMetadata(
        title="A Study of Feedback Systems",
        authors=["Ada Lovelace", "Grace Hopper"] if complete else [],
        year=2025 if complete else None,
        source_name="arXiv" if complete else "",
        url="https://arxiv.org/abs/2501.00001",
        identifier="arXiv:2501.00001" if complete else None,
        abstract_excerpt="We compare feedback systems in a controlled learning study.",
        accessed_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


def _conversation_with_evidence(
    client: TestClient, *, complete: bool = True
) -> tuple[str, dict[str, object]]:
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    source = FakeArxivSource(_paper(complete=complete))
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    conversation = client.post(
        "/api/v1/research/conversations", json={"initial_message": "我研究 Python 反馈"}
    ).json()
    conversation_id = conversation["conversation_id"]
    bundle = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"query": "Python feedback", "sources": ["arxiv"]},
    )
    assert bundle.status_code == 200
    assert source.calls == 1
    return conversation_id, bundle.json()


def _selection(bundle: dict[str, object]) -> dict[str, str]:
    paper = bundle["papers"][0]
    return {
        "evidence_bundle_id": str(bundle["bundle_id"]),
        "paper_url": str(paper["url"]),
        "target_document": "paper_blueprint",
        "target_section": "相关工作",
        "paragraph_anchor": "相关工作-1",
        "user_note": "待导师核对引用位置",
    }


def test_citation_candidates_are_derived_only_from_saved_conversation_evidence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation_id, bundle = _conversation_with_evidence(client)
    monkeypatch.setattr(
        _conversation_search_service,
        "search",
        lambda *_args, **_kwargs: pytest.fail("查看引用候选不得发起检索"),
    )

    candidates = client.get(f"/api/v1/research/conversations/{conversation_id}/citation-candidates")
    references = client.get(
        f"/api/v1/research/conversations/{conversation_id}/reference-entry-drafts"
    )

    assert candidates.status_code == 200
    assert candidates.json()[0]["evidence_bundle_id"] == bundle["bundle_id"]
    assert candidates.json()[0]["classification"] == "fact"
    assert candidates.json()[0]["source_scope"] == "metadata_and_abstract_only"
    assert references.status_code == 200
    assert references.json() == []


def test_selected_citation_persists_placeholder_and_never_overwrites_draft(
    client: TestClient,
) -> None:
    conversation_id, bundle = _conversation_with_evidence(client)
    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/selected-citations",
        json=_selection(bundle),
    )
    restored = client.get(f"/api/v1/research/conversations/{conversation_id}/selected-citations")
    references = client.get(
        f"/api/v1/research/conversations/{conversation_id}/reference-entry-drafts"
    )

    assert created.status_code == 201
    selected = created.json()
    assert selected["target_section"] == "相关工作"
    assert selected["citation_placeholder"] == "(Lovelace et al., 2025)"
    assert selected["status"] == "selected"
    assert restored.json()[0]["selected_citation_id"] == selected["selected_citation_id"]
    assert references.json()[0]["display_text"].startswith("Lovelace, A.; Hopper, G. (2025).")
    assert references.json()[0]["source_scope"] == "metadata_and_abstract_only"
    assert client.get(f"/api/v1/research/conversations/{conversation_id}/paper-drafts").json() == []


def test_incomplete_metadata_stays_to_verify_and_other_conversations_cannot_select_it(
    client: TestClient,
) -> None:
    conversation_id, bundle = _conversation_with_evidence(client, complete=False)
    other_conversation_id, _other_bundle = _conversation_with_evidence(client)

    selected = client.post(
        f"/api/v1/research/conversations/{conversation_id}/selected-citations",
        json=_selection(bundle),
    )
    cross_session = client.post(
        f"/api/v1/research/conversations/{other_conversation_id}/selected-citations",
        json=_selection(bundle),
    )

    assert selected.status_code == 201
    reference = selected.json()["reference_entry"]
    assert reference["classification"] == "to_verify"
    assert "作者" in "\n".join(reference["to_verify_items"])
    assert "年份" in "\n".join(reference["to_verify_items"])
    assert "来源" in "\n".join(reference["to_verify_items"])
    assert selected.json()["citation_placeholder"] == "[引用待核对：A Study of Feedback Systems]"
    assert cross_session.status_code == 404


def test_user_can_skip_a_selected_citation_without_automatic_insertion(client: TestClient) -> None:
    conversation_id, bundle = _conversation_with_evidence(client)
    selected = client.post(
        f"/api/v1/research/conversations/{conversation_id}/selected-citations",
        json=_selection(bundle),
    ).json()

    skipped = client.patch(
        f"/api/v1/research/selected-citations/{selected['selected_citation_id']}",
        json={"status": "skipped"},
    )
    references = client.get(
        f"/api/v1/research/conversations/{conversation_id}/reference-entry-drafts"
    )

    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped"
    assert references.json() == []
